from __future__ import annotations

from datetime import datetime
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import httpx
import requests
from bs4 import BeautifulSoup
from app.config import scraper_settings

# =========================
# Exceptions
# =========================
class EclassError(Exception):
    """Base exception for this client."""


class LoginFailed(EclassError):
    """Credentials wrong, SSO-only account, or login page returned again."""


class AuthExpired(EclassError):
    """Session expired / not logged in when accessing protected resource."""


class BlockedOrForbidden(EclassError):
    """403 or WAF block / forbidden."""


class RateLimited(EclassError):
    """429 Too many requests."""


class TemporaryServerError(EclassError):
    """5xx errors that are likely temporary."""


# =========================
# Config
# =========================
@dataclass(frozen=True)
class EclassClientConfig:
    base_url = scraper_settings.base_url
    login_index_url = scraper_settings.login_index_url
    timeout: float = 20.0

    # Retries
    max_retries: int = 4
    backoff_base: float = 0.6     # seconds
    backoff_jitter: float = 0.25  # seconds

    user_agent: str = "EclassLightClient/1.2"


# =========================
# Client
# =========================
class EclassClient:
    def __init__(self, cfg: EclassClientConfig = EclassClientConfig()) -> None:
        self.cfg = cfg
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        # Custom short keys you want
        self.subject_aliases: Dict[str, str] = {
            "Discrete Mathematics": "DM",
            "Academic English 4": "AE4",
        }

        self.cfg = cfg
        self.timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
        self.client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )

    async def aclose(self):
        await self.client.aclose()
    
    def _find_quiz_url(self, course_page_html: str) -> Optional[str]:
        """
        Finds the Quiz index URL on the course page.
        Example:
        https://eclass.inha.ac.kr/mod/quiz/index.php?id=2377
        Returns None if hidden/not present.
        """
        soup = self._soup(course_page_html)

        # Most reliable: href contains /mod/quiz/index.php?id=
        a = soup.select_one('a[href*="/mod/quiz/index.php?id="]')
        if a and a.get("href"):
            return urljoin(self.cfg.base_url, a["href"])

        # Fallback: any <a> whose visible text is "Quiz"
        for a in soup.select("a[href]"):
            if (a.get_text(strip=True) or "").lower() == "quiz":
                href = a.get("href")
                if href and "/mod/quiz/index.php" in href:
                    return urljoin(self.cfg.base_url, href)

        return None

    def _get_quiz_status(self, quiz_url: str) -> str:
        """Checks if a quiz has been submitted by looking for the attempt summary."""
        try:
            r = self._request("GET", quiz_url)
            soup = self._soup(r.text)
            
            # If the "Summary of your previous attempts" table exists, it's submitted
            if soup.select_one("table.generaltable") or soup.select_one(".quizattemptsummary"):
                return "Submitted"
            
            # If specific 'No attempts' text is found, it's not submitted
            page_text = soup.get_text().lower()
            if "no attempts have been made yet" in page_text:
                return "Not submitted"
                
            # If an "Attempt quiz now" button exists without a summary table
            if soup.find("input", value=re.compile(r"Attempt", re.I)):
                return "Not submitted"
        except:
            pass
        return "Not submitted"
    def _parse_quiz_index_page(self, quiz_index_html: str, quiz_index_url: str) -> List[Dict[str, Any]]:
        """
        Parses /mod/quiz/index.php?id=COURSE_ID
        Extracts: Week, Name (+url), Quiz closes, Grade.
        """
        soup = self._soup(quiz_index_html)
        table = soup.select_one("table.generaltable")
        if not table:
            return []

        quizzes: List[Dict[str, Any]] = []
        for tr in table.select("tbody tr"):
            tds = tr.select("td")
            if len(tds) < 4:
                continue

            week = tds[0].get_text(" ", strip=True) or None

            name_a = tds[1].select_one("a[href]")
            if not name_a:
                continue
            name = name_a.get_text(" ", strip=True)

            # Important: sometimes link is relative like "view.php?id=64861"
            # Use quiz_index_url as base so it becomes /mod/quiz/view.php?id=...
            quiz_url = urljoin(quiz_index_url, name_a["href"])

            closes = tds[2].get_text(" ", strip=True) or None
            grade = tds[3].get_text(" ", strip=True) or None
            quiz_url = urljoin(quiz_index_url, name_a["href"])
            status = self._get_quiz_status(quiz_url)
            quizzes.append({
                "week": week,
                "name": name,
                "quiz_closes": closes,
                "grade": grade,
                "url": quiz_url,
                "status":status
            })

        return quizzes


    def get_quizzes_for_course(self, course_page_html: str) -> Optional[List[Dict[str, Any]]]:
        """
        From a course page HTML:
        - If Quiz link exists -> returns list of quizzes (maybe empty).
        - If hidden/missing -> returns None.
        """
        quiz_index_url = self._find_quiz_url(course_page_html)
        if not quiz_index_url:
            return None

        r = self._request("GET", quiz_index_url)
        if not self._is_logged_in_html(r.text):
            raise AuthExpired("Not logged in while opening quiz page.")

        return self._parse_quiz_index_page(r.text, quiz_index_url)

    # ---------- request + retry ----------
    def _sleep_backoff(self, attempt: int) -> None:
        base = self.cfg.backoff_base * (2 ** attempt)
        jitter = random.uniform(0, self.cfg.backoff_jitter)
        time.sleep(base + jitter)

    def _request(self, method: str, url: str, *, allow_redirects: bool = True, **kwargs) -> requests.Response:
        last_exc: Optional[Exception] = None

        for attempt in range(self.cfg.max_retries):
            try:
                r = self.s.request(
                    method,
                    url,
                    timeout=self.cfg.timeout,
                    allow_redirects=allow_redirects,
                    **kwargs,
                )

                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        time.sleep(int(ra))
                    else:
                        self._sleep_backoff(attempt)
                    last_exc = RateLimited(f"429 Rate limited at {url}")
                    continue

                if r.status_code == 403:
                    if attempt < self.cfg.max_retries - 1:
                        self._sleep_backoff(attempt)
                        last_exc = BlockedOrForbidden(f"403 Forbidden at {url}")
                        continue
                    raise BlockedOrForbidden(f"403 Forbidden at {url}")

                if 500 <= r.status_code <= 599:
                    if attempt < self.cfg.max_retries - 1:
                        self._sleep_backoff(attempt)
                        last_exc = TemporaryServerError(f"{r.status_code} Server error at {url}")
                        continue
                    raise TemporaryServerError(f"{r.status_code} Server error at {url}")

                r.raise_for_status()
                return r

            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                if attempt < self.cfg.max_retries - 1:
                    self._sleep_backoff(attempt)
                    continue
                raise EclassError(f"Network error calling {url}: {e}") from e

            except requests.HTTPError as e:
                raise EclassError(f"HTTP error calling {url}: {e}") from e

        raise EclassError(f"Request failed after retries: {method} {url}. Last error: {last_exc}")

    # ---------- html helpers ----------
    @staticmethod
    def _soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @classmethod
    def _is_logged_in_html(cls, html: str) -> bool:
        soup = cls._soup(html)
        if soup.select_one('a[href*="/login/logout.php"]'):
            return True
        if soup.select_one(".userpicture") and soup.select_one(".usermenu"):
            return True
        return False

    @classmethod
    def _looks_like_login_page(cls, html: str) -> bool:
        soup = cls._soup(html)
        return (
            soup.select_one("form.form-login") is not None
            or soup.select_one('input[type="password"][name="password"]') is not None
        )

    @classmethod
    def _extract_login_error(cls, html: str) -> Optional[str]:
        soup = cls._soup(html)
        err = soup.select_one(".loginerrors, .error, .alert, .alert-danger")
        if err:
            msg = err.get_text(" ", strip=True)
            return msg or None
        return None

    # =========================
    # Login
    # =========================
    def login(self, username: str, password: str) -> None:
        r1 = self._request("GET", self.cfg.login_index_url)
        soup = self._soup(r1.text)

        form = soup.select_one("form.mform.form-login")
        if not form:
            raise LoginFailed("Login form not found on /login/index.php (layout changed or blocked).")

        action = form.get("action") or self.cfg.login_index_url
        post_url = urljoin(self.cfg.base_url, action)

        payload: Dict[str, str] = {}
        for inp in form.select("input[name]"):
            name = inp.get("name")
            if not name:
                continue
            itype = (inp.get("type") or "").lower()
            if itype == "hidden":
                payload[name] = inp.get("value", "")

        payload["username"] = username
        payload["password"] = password

        submit = form.select_one('input[type="submit"][name]')
        if submit and submit.get("name"):
            payload[submit["name"]] = submit.get("value", "Log in")

        r2 = self._request(
            "POST",
            post_url,
            data=payload,
            headers={
                "Origin": self.cfg.base_url.rstrip("/"),
                "Referer": r1.url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if self._is_logged_in_html(r2.text):
            return

        home = self._request("GET", self.cfg.base_url)
        if self._is_logged_in_html(home.text):
            return

        err = self._extract_login_error(r2.text) or self._extract_login_error(home.text)
        if err:
            raise LoginFailed(f"Login failed: {err}")

        if self._looks_like_login_page(home.text) or "login" in (home.url or ""):
            raise LoginFailed(f"Login failed: ended at {home.url}")

        raise LoginFailed("Login failed for unknown reason (no error message found).")

    def _ensure_logged_in(self) -> None:
        home = self._request("GET", self.cfg.base_url)
        if not self._is_logged_in_html(home.text):
            raise AuthExpired("Not logged in (session expired or login failed).")




    async def check_credentials(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        try:
            # 1) GET login page (to get hidden tokens)
            r1 = await self.client.get(self.cfg.login_index_url)
            soup = self._soup(r1.text)

            form = soup.select_one("form.mform.form-login")
            if not form:
                return False, "Login form not found (layout changed or blocked)."

            action = form.get("action") or self.cfg.login_index_url
            post_url = urljoin(self.cfg.base_url, action)

            payload: Dict[str, str] = {}
            for inp in form.select("input[name]"):
                name = inp.get("name")
                if not name:
                    continue
                if (inp.get("type") or "").lower() == "hidden":
                    payload[name] = inp.get("value", "")

            payload["username"] = username
            payload["password"] = password

            submit = form.select_one('input[type="submit"][name]')
            if submit and submit.get("name"):
                payload[submit["name"]] = submit.get("value", "Log in")

            # 2) POST login
            r2 = await self.client.post(
                post_url,
                data=payload,
                headers={
                    "Origin": self.cfg.base_url.rstrip("/"),
                    "Referer": str(r1.url),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            # Decide quickly
            if self._is_logged_in_html(r2.text):
                return True, None

            err = self._extract_login_error(r2.text)
            if err:
                return False, err

            # Optional: one more check (sometimes login redirects)
            home = await self.client.get(self.cfg.base_url)
            if self._is_logged_in_html(home.text):
                return True, None

            if self._looks_like_login_page(home.text):
                return False, "Invalid username or password."

            return False, "Login failed (unknown)."

        except httpx.TimeoutException:
            return False, "Timeout connecting to eClass."
        except httpx.HTTPError:
            return False, "Network error connecting to eClass."
        

        
    # =========================
    # Courses
    # =========================
    def get_courses(self) -> List[Tuple[str, str]]:
        r = self._request("GET", self.cfg.base_url)
        if not self._is_logged_in_html(r.text):
            raise AuthExpired("Not logged in (cannot fetch courses).")

        soup = self._soup(r.text)
        courses: List[Tuple[str, str]] = []
        for a in soup.select("ul.my-course-lists a.course_link"):
            href = a.get("href")
            title_el = a.select_one("h3")
            title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
            if href and title:
                courses.append((title, urljoin(self.cfg.base_url, href)))
        return courses

    # =========================
    # Subject key (DM, AE4, CA, etc.)
    # =========================
    @staticmethod
    def _strip_brackets(full_title: str) -> str:
        """
        "Digital Logic Circuit[202601-SOC2020-004] NEW" -> "Digital Logic Circuit"
        """
        s = full_title.strip()

        # remove trailing [....]
        s = re.sub(r"\s*\[.*?\]\s*$", "", s).strip()

        # sometimes NEW is after brackets or before; remove it too
        s = re.sub(r"\s+\bNEW\b\s*$", "", s, flags=re.IGNORECASE).strip()

        return s

    def make_subject_key(self, full_title: str) -> str:
        base = self._strip_brackets(full_title)

        # custom aliases first
        for k, v in self.subject_aliases.items():
            if base.lower() == k.lower():
                return v

        # keep trailing number like "...-1" or "... 1"
        m_tail = re.search(r"(?:[-\s])(\d+)\s*$", base)
        tail_num = m_tail.group(1) if m_tail else ""

        name_part = base
        if tail_num:
            name_part = re.sub(r"(?:[-\s])\d+\s*$", "", base).strip()

        # words
        words = re.findall(r"[A-Za-z]+", name_part)

        # stopwords
        skip = {"of", "and", "the", "in", "to", "a", "an", "for", "on", "with", "by", "at"}

        initials = "".join(w[0].upper() for w in words if w.lower() not in skip)

        if not initials:
            initials = "SB"

        return f"{initials}{tail_num}"

    @staticmethod
    def _clean_text(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    def _find_professor_name(self, soup: BeautifulSoup) -> Optional[str]:
        for h4 in soup.select("h4.media-heading"):
            name = self._clean_text(h4.get_text(" ", strip=True))
            if 2 <= len(name.split()) <= 4 and len(name) <= 80:
                return name
        return None

    @staticmethod
    def _course_id_from_url(url: str) -> Optional[str]:
        try:
            q = parse_qs(urlparse(url).query)
            cid = q.get("id", [None])[0]
            return str(cid) if cid else None
        except Exception:
            return None

    # =========================
    # Attendance URL finders
    # =========================
    def _find_offline_attendance_url(self, soup: BeautifulSoup) -> Optional[str]:
        a = soup.select_one('a.submenu-attendance[href]')
        if a and a.get("href"):
            return urljoin(self.cfg.base_url, a["href"])

        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            if "local/ubattendance/my_status.php" in href:
                return urljoin(self.cfg.base_url, href)

        for a in soup.select("a[href]"):
            if "offline-attendance" in (a.get_text(" ", strip=True) or "").lower():
                return urljoin(self.cfg.base_url, a.get("href") or "")

        return None

    def _find_online_attendance_url(self, soup: BeautifulSoup) -> Optional[str]:
        a = soup.select_one('a.submenu-progress[href]')
        if a and a.get("href"):
            return urljoin(self.cfg.base_url, a["href"])

        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            if "report/ubcompletion/progress.php" in href:
                return urljoin(self.cfg.base_url, href)

        for a in soup.select("a[href]"):
            if "online-attendance" in (a.get_text(" ", strip=True) or "").lower():
                return urljoin(self.cfg.base_url, a.get("href") or "")

        return None

    # =========================
    # Attendance parsers
    # =========================
    @staticmethod
    def _find_course_not_set_message(soup: BeautifulSoup) -> Optional[str]:
        err = soup.select_one(".alert.alert-danger .error_message, .alert.alert-danger, .error_message")
        if not err:
            return None
        msg = err.get_text(" ", strip=True)
        if "course has not been set" in msg.lower():
            return msg
        if "has not been set" in msg.lower() and "course" in msg.lower():
            return msg
        return None

    def _parse_online_attendance_page(self, html: str) -> Dict[str, Any]:
        soup = self._soup(html)

        # If attendance not configured / page error
        danger = soup.select_one(".alert.alert-danger, .alert-danger, .error_message")
        if danger:
            msg = danger.get_text(" ", strip=True)
            if "not been set" in msg.lower() or "not set" in msg.lower():
                return {"status": "attendance_not_set", "message": msg, "counts": {}}

        # This block exists either in progress page OR sometimes only in course home page
        box = soup.select_one("div.user_attendance_table div.att_count, div.user_attendance div.att_count, div.att_count")
        if not box:
            return {"status": "attendance_unknown_format", "message": "Online attendance block not found.", "counts": {}}

        # Always return full structure
        counts: Dict[str, int] = {"attendance": 0, "absence": 0, "late": 0}

        # Parse by LABEL text (NOT by count01/count02/count03)
        # Example: <p class="count02">Absence<span> 1</span></p>
        for p in box.select("p"):
            span = p.select_one("span")
            if not span:
                continue

            # label = text before the span
            label = p.get_text(" ", strip=True)
            # remove the span number part from label safely
            # easiest: take p.text, then remove span.text
            span_text = span.get_text(" ", strip=True)
            label = label.replace(span_text, "").strip().strip(":").lower()

            m = re.search(r"\d+", span_text)
            if not m:
                # sometimes number could be in full p text
                m = re.search(r"\d+", p.get_text(" ", strip=True))
            if not m:
                continue

            num = int(m.group(0))

            if "attendance" in label:
                counts["attendance"] = num
            elif "absence" in label:
                counts["absence"] = num
            elif "late" in label:
                counts["late"] = num

        # If we still didn't detect anything meaningful, return unknown format
        if counts == {"attendance": 0, "absence": 0, "late": 0}:
            # still could be real zeros, so check if any number existed at all
            any_number = bool(re.search(r"\d+", box.get_text(" ", strip=True)))
            if not any_number:
                return {"status": "attendance_unknown_format", "message": "Online attendance counts not found.", "counts": {}}

        return {"status": "ok", "message": "", "counts": counts}




    

    def _parse_offline_attendance_rows(self, html: str) -> dict:
        soup = self._soup(html)

        table = soup.select_one("table.attendance_my")
        if not table:
            return {"records": [], "totals": {"attendance": 0, "absence": 0, "late": 0}}

        records = []
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue

            week_str = tds[0].get_text(strip=True)  # "2026-02-16"
            class_name = tds[1].get_text(" ", strip=True) or None

            att_mark = tds[2].get_text(strip=True)  # "○" or ""
            abs_mark = tds[3].get_text(strip=True)
            late_mark = tds[4].get_text(strip=True)

            def is_marked(x: str) -> bool:
                return (x or "").strip() in {"○", "O", "o", "◯"}

            date_of_week = None
            try:
                date_of_week = datetime.strptime(week_str, "%Y-%m-%d").date().isoformat()
            except Exception:
                date_of_week = week_str  # fallback keep raw

            records.append({
                "date_of_week": date_of_week,
                "class_name": class_name,
                "attendance": is_marked(att_mark),
                "absence": is_marked(abs_mark),
                "late": is_marked(late_mark),
            })

        # totals from tfoot
        totals = {"attendance": 0, "absence": 0, "late": 0}
        tfoot = table.select_one("tfoot")
        if tfoot:
            txt = tfoot.get_text(" ", strip=True)

            def grab(label: str) -> int:
                m = re.search(rf"{label}\s*:\s*(\d+)", txt, flags=re.I)
                return int(m.group(1)) if m else 0

            totals["attendance"] = grab("Attendance")
            totals["absence"] = grab("Absence")
            totals["late"] = grab("Late")

        return {"records": records, "totals": totals}

    def _parse_offline_attendance_page(self, html: str) -> Dict[str, Any]:
        soup = self._soup(html)

        danger = soup.select_one(".alert.alert-danger, .alert-danger, .error_message")
        if danger:
            msg = danger.get_text(" ", strip=True)
            if "not been set" in msg.lower() or "not set" in msg.lower():
                return {"status": "attendance_not_set", "message": msg, "counts": {}}

        text = soup.get_text("\n", strip=True)

        box = soup.select_one("div.att_count")
        if box:
            def grab(cls_name: str) -> Optional[int]:
                p = box.select_one(f"p.{cls_name} span")
                if not p:
                    return None
                m = re.search(r"\d+", p.get_text(" ", strip=True))
                return int(m.group(0)) if m else None

            attendance = grab("count01")
            absence = grab("count02")
            late = grab("count03")

            counts: Dict[str, int] = {}
            if attendance is not None:
                counts["attendance"] = attendance
            if absence is not None:
                counts["absence"] = absence
            if late is not None:
                counts["late"] = late

            if counts:
                return {"status": "ok", "message": "", "counts": counts}

        def find_label(label: str) -> Optional[int]:
            rx = re.compile(rf"\b{re.escape(label)}\b\s*[:\(\-]?\s*(\d+)", re.IGNORECASE)
            m = rx.search(text)
            return int(m.group(1)) if m else None

        attendance = find_label("Attendance")
        absence = find_label("Absence")
        late = find_label("Late")

        counts2: Dict[str, int] = {}
        if attendance is not None:
            counts2["attendance"] = attendance
        if absence is not None:
            counts2["absence"] = absence
        if late is not None:
            counts2["late"] = late

        if counts2:
            return {"status": "ok", "message": "", "counts": counts2}

        return {"status": "attendance_unknown_format", "message": "Offline attendance format not recognized.", "counts": {}}

    # =========================
    # Main per-course fetch
    # =========================
    # =========================
    # NEW: Assignments URL finder
    # =========================
    def _find_assignment_url(self, soup: BeautifulSoup) -> Optional[str]:
      
        # Most reliable: match the assign index pattern
        a = soup.select_one('a[href*="/mod/assign/index.php?id="]')
        if a and a.get("href"):
            return urljoin(self.cfg.base_url, a["href"])

        # Fallback: visible text "Assignment"
        for a in soup.select("a[href]"):
            if (a.get_text(" ", strip=True) or "").strip().lower() == "assignment":
                href = a.get("href") or ""
                if "/mod/assign/index.php" in href:
                    return urljoin(self.cfg.base_url, href)

        return None

    # =========================
    # NEW: Assignments parser
    # =========================
    def _parse_assignments_index_page(self, html: str) -> Dict[str, Any]:
  
        soup = self._soup(html)

        table = soup.select_one("table.generaltable")
        if not table:
            return {
                "status": "assignments_unknown_format",
                "message": "Assignments table not found.",
                "items": [],
            }

        items: List[Dict[str, Any]] = []
        tbody = table.select_one("tbody")
        if not tbody:
            return {
                "status": "assignments_unknown_format",
                "message": "Assignments table body not found.",
                "items": [],
            }

        for tr in tbody.select("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue  # divider rows etc.

            week = tds[0].get_text(" ", strip=True)

            a = tds[1].select_one("a[href]")
            title = a.get_text(" ", strip=True) if a else tds[1].get_text(" ", strip=True)
            asg_url = urljoin(self.cfg.base_url, a["href"]) if a and a.get("href") else None

            due_date = tds[2].get_text(" ", strip=True)
            submission = tds[3].get_text(" ", strip=True)
            grade = tds[4].get_text(" ", strip=True)

            # Ignore totally empty junk rows
            if not (week or title or due_date or submission or grade):
                continue

            items.append(
                {
                    "week": week,
                    "title": title,
                    "due_date": due_date,
                    "submission": submission,
                    "grade": grade,
                    "url": asg_url,
                }
            )

        return {"status": "ok", "message": "", "items": items}

    # =========================
    # REWRITE: get_attendance_for_course (UPGRADED)
    # =========================
    from urllib.parse import urljoin
    import re
    def _check_quiz_submission(self, quiz_url: str) -> str:
        """Visits individual quiz page to check if an attempt exists."""
        try:
            r = self._request("GET", quiz_url)
            soup = self._soup(r.text)
            
            # Check for the summary header (most reliable)
            summary_header = soup.find(lambda tag: tag.name == "h3" and "Summary of your previous attempts" in tag.text)
            if summary_header:
                return "Submitted"
            
            # Fallback: check for "No attempts have been made yet" text
            if soup.find(string=re.compile(r"No attempts have been made yet", re.I)):
                return "Not submitted"
            
            return "Unknown"
        except Exception:
            return "Error checking status"
    def get_attendance_for_course(self, subject_title: str, course_url: str):
        """
        Returns ONE course object with:
        - attendance totals: {"attendance": int, "absence": int, "late": int} or None
        - attendance_records (offline rows): [
                {"date_of_week": "YYYY-MM-DD", "class_name": str|None,
                "attendance": bool, "absence": bool, "late": bool}
            ] or None
        - attendanceUrl, attendanceKind
        - assignments, quizzes
        - courseUrl, subjectNameFull, subjectKey, subjectName
        """

        # 1) Open course page
        r = self._request("GET", course_url)
        course_html = r.text
        if not self._is_logged_in_html(course_html):
            raise AuthExpired("Session expired while opening course page.")

        soup = self._soup(course_html)
        professor_name = self._find_professor_name(soup)

        # 2) Subject name (full) + clean
        h1_a = soup.select_one(".coursename h1 a")
        subject_name_full = h1_a.get_text(" ", strip=True) if h1_a else subject_title
        subject_name_clean = subject_name_full.split("[", 1)[0].strip()

        # 3) subjectKey from initials (your current logic)
        words = [w for w in subject_name_clean.replace("-", " ").split() if w.strip()]
        subject_key = "".join([w[0].upper() for w in words]) if words else subject_title

        # 4) Detect attendance link (offline or online)
        attendance_url = None
        attendance_kind = None

        a_off = soup.select_one('a[href*="/local/ubattendance/my_status.php?id="]')
        a_on = soup.select_one('a[href*="/report/ubcompletion/progress.php?id="]')

        # fallback by menu text
        if not a_off:
            for a in soup.select("a[href]"):
                txt = (a.get_text(" ", strip=True) or "").lower()
                href = a.get("href", "")
                if ("offline-attendance" in txt or "offline attendance" in txt) and "/local/ubattendance/my_status.php" in href:
                    a_off = a
                    break

        if not a_on:
            for a in soup.select("a[href]"):
                txt = (a.get_text(" ", strip=True) or "").lower()
                href = a.get("href", "")
                if ("online-attendance" in txt or "online attendance" in txt) and "/report/ubcompletion/progress.php" in href:
                    a_on = a
                    break

        if a_off and a_off.get("href"):
            attendance_url = urljoin(course_url, a_off["href"])
            attendance_kind = "offline"
        elif a_on and a_on.get("href"):
            attendance_url = urljoin(course_url, a_on["href"])
            attendance_kind = "online"

        # 5) Parse attendance totals + rows (rows only for offline)
        attendance_counts = None
        attendance_records = None

        if attendance_url:
            rr = self._request("GET", attendance_url)
            att_html = rr.text

            if not self._is_logged_in_html(att_html):
                raise AuthExpired("Session expired while opening attendance page.")

            att_soup = self._soup(att_html)

            if attendance_kind == "offline":
                # ---- parse rows ----
                table = att_soup.select_one("table.attendance_my")
                if table:
                    def is_marked(x: str) -> bool:
                        return (x or "").strip() in {"○", "O", "o", "◯"}

                    attendance_records = []
                    for tr in table.select("tbody tr"):
                        tds = tr.find_all("td")
                        if len(tds) < 5:
                            continue

                        week_str = tds[0].get_text(strip=True)  # "2026-02-16"
                        class_name = tds[1].get_text(" ", strip=True) or None

                        att_mark = tds[2].get_text(strip=True)
                        abs_mark = tds[3].get_text(strip=True)
                        late_mark = tds[4].get_text(strip=True)

                        # date normalize
                        date_of_week = week_str
                        try:
                            date_of_week = datetime.strptime(week_str, "%Y-%m-%d").date().isoformat()
                        except Exception:
                            pass

                        attendance_records.append({
                            "date_of_week": date_of_week,
                            "class_name": class_name,
                            "attendance": is_marked(att_mark),
                            "absence": is_marked(abs_mark),
                            "late": is_marked(late_mark),
                        })

                    # ---- parse totals from tfoot ----
                    tfoot = table.select_one("tfoot")
                    if tfoot:
                        txt = tfoot.get_text(" ", strip=True)

                        def grab(label: str) -> int:
                            m = re.search(rf"{label}\s*:\s*(\d+)", txt, flags=re.I)
                            return int(m.group(1)) if m else 0

                        attendance_counts = {
                            "attendance": grab("Attendance"),
                            "absence": grab("Absence"),
                            "late": grab("Late"),
                        }

            elif attendance_kind == "online":
                # online totals block
                box = (
                    soup.select_one("div.user_attendance div.att_count")
                    or soup.select_one("div.att_count")
                    or att_soup.select_one("div.user_attendance div.att_count")
                    or att_soup.select_one("div.att_count")
                )

                if box:
                    attendance_counts = {"attendance": 0, "absence": 0, "late": 0}

                    for p in box.find_all("p"):
                        text = p.get_text(" ", strip=True).lower()
                        span = p.find("span")
                        if not span:
                            continue

                        try:
                            val = int(re.search(r"\d+", span.get_text(strip=True)).group(0))
                        except Exception:
                            val = 0

                        if any(k in text for k in ["attendance", "출석", "present"]):
                            attendance_counts["attendance"] = val
                        elif any(k in text for k in ["absence", "결석"]):
                            attendance_counts["absence"] = val
                        elif any(k in text for k in ["late", "지각"]):
                            attendance_counts["late"] = val

        # 6) ASSIGNMENTS (your existing logic)
        assignments = None
        assign_a = soup.select_one('a[href*="/mod/assign/index.php?id="]')
        if not assign_a:
            for a in soup.select("a[href]"):
                if (a.get_text(strip=True) or "").lower() == "assignment":
                    if "/mod/assign/index.php" in a.get("href", ""):
                        assign_a = a
                        break

        if assign_a and assign_a.get("href"):
            assign_index_url = urljoin(course_url, assign_a["href"])
            rr = self._request("GET", assign_index_url)
            assign_html = rr.text
            if not self._is_logged_in_html(assign_html):
                raise AuthExpired("Session expired while opening assignment page.")

            assign_soup = self._soup(assign_html)
            table = assign_soup.select_one("table.generaltable")
            assignments = []

            if table:
                for tr in table.select("tbody tr"):
                    tds = tr.select("td")
                    if len(tds) < 5:
                        continue

                    week = tds[0].get_text(" ", strip=True) or None
                    a = tds[1].select_one("a[href]")
                    if not a:
                        continue

                    name = a.get_text(" ", strip=True)
                    url = urljoin(assign_index_url, a["href"])
                    due_date = tds[2].get_text(" ", strip=True) or None
                    submission = tds[3].get_text(" ", strip=True) or None
                    grade = tds[4].get_text(" ", strip=True) or None

                    assignments.append({
                        "week": week,
                        "name": name,
                        "due_date": due_date,
                        "submission": submission,
                        "grade": grade,
                        "url": url,
                    })

        # NOTE: your quizzes part is below in your file; keep it as-is (or paste it here if you want me to merge too)

        return {
            "subjectKey": subject_key,
            "subjectNameFull": subject_name_full,
            "subjectName": subject_name_clean,
            "courseUrl": course_url,
            "professorName": professor_name,

            "attendanceUrl": attendance_url,
            "attendanceKind": attendance_kind,
            "attendance": attendance_counts,              # totals or None
            "attendance_records": attendance_records,     # list or None (offline only)

            "assignments": assignments,
            # keep your existing quizzes logic and include it in return if you have it:
            # "quizzes": quizzes,
        }









    # =========================
    # Bulk fetch (keeps going)
    # =========================
    from typing import List, Dict, Any

    def get_all_attendance(self) -> Dict[str, Any]:
        self._ensure_logged_in()
        courses = self.get_courses()  # <-- your existing function (list of (title, url))

        subjects: List[Dict[str, Any]] = []

        for title, url in courses:
            try:
                info = self.get_attendance_for_course(title, url)

                # ---- subject short key ----
                # Prefer already computed key if present, else make one
                subject_key = (
                    info.get("subject")
                    or info.get("subjectKey")
                    or self.make_subject_key(title)
                )

                # ---- subject full name ----
                # Prefer cleaned name if present, else clean from full title
                subject_name = (
                    info.get("subject_name")
                    or info.get("subjectName")
                    or info.get("subjectNameFull")
                    or title
                )

                # If name includes "[...]" cut it off
                if isinstance(subject_name, str) and "[" in subject_name:
                    subject_name = subject_name.split("[", 1)[0].strip()

                # ---- attendance normalize ----
                att = info.get("attendance") or {}
                attendance = {
                    "attendance": int(att.get("attendance", 0) or 0),
                    "absence": int(att.get("absence", 0) or 0),
                    "late": int(att.get("late", 0) or 0),
                }

                subjects.append({
                "subject": subject_key,
                "subject_name": subject_name,
                "professor_name": info.get("professorName"),
                "course_url": info.get("course_url") or info.get("courseUrl") or url,
                "attendance": attendance,  # totals
                "attendance_records": info.get("attendance_records"),  # ✅ per-date rows (offline)
                "assignments": info.get("assignments", None),
                "quizzes": info.get("quizzes", None),
            })


            except (RateLimited, BlockedOrForbidden, TemporaryServerError) as e:
                subjects.append({
                    "subject": self.make_subject_key(title),
                    "subject_name": title.split("[", 1)[0].strip() if "[" in title else title,
                    "course_url": url,
                    "attendance": {"attendance": 0, "absence": 0, "late": 0},
                    "attendance_records": None,
                    "assignments": None,
                    "quizzes": None,
                    "status": "request_failed",
                    "message": str(e),
                })

            except AuthExpired as e:
                subjects.append({
                    "subject": self.make_subject_key(title),
                    "subject_name": title.split("[", 1)[0].strip() if "[" in title else title,
                    "course_url": url,
                    "attendance": {"attendance": 0, "absence": 0, "late": 0},
                    "attendance_records": None,
                    "assignments": None,
                    "quizzes": None,
                    "status": "auth_expired",
                    "message": str(e),
                })

            except Exception as e:
                subjects.append({
                    "subject": self.make_subject_key(title),
                    "subject_name": title.split("[", 1)[0].strip() if "[" in title else title,
                    "course_url": url,
                    "attendance": {"attendance": 0, "absence": 0, "late": 0},
                    "attendance_records": None,
                    "assignments": None,
                    "quizzes": None,
                    "status": "unexpected_error",
                    "message": repr(e),
                })

        # IMPORTANT: no self.student_id access, since your class doesn't have it
        return {
            "subjects": subjects
        }


# =========================
# Output packer (YOUR structure)
# subjects is LIST (not dict)
# =========================
from typing import Any, Dict, List

def pack_student_rest(student_id: str, data: dict) -> dict:
    """
    data = {
      "subjects": [ {...}, {...} ]
    }
    """

    return {
        "student_id": student_id,
        "subjects": data.get("subjects", [])
    }





# if __name__ == "__main__":
#     c = EclassClient()

#    

#     try:
#         c.login(USERNAME, PASSWORD)

#         rows = c.get_all_attendance()

#         final_json = pack_student_rest(USERNAME, rows)
#         pprint(final_json)

#     except LoginFailed as e:
#         print("LOGIN FAILED:", e)
#     except RateLimited as e:
#         print("RATE LIMITED:", e)
#     except BlockedOrForbidden as e:
#         print("FORBIDDEN/BLOCKED:", e)
#     except AuthExpired as e:
#         print("AUTH EXPIRED:", e)
#     except EclassError as e:
#         print("GENERAL ERROR:", e)

