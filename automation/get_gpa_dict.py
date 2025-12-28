import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()

# 🔒 GLOBAL CONCURRENCY LIMIT (VERY IMPORTANT)
SCRAPE_LIMIT = asyncio.Semaphore(5)

def normalize_redirect(location, base_host="ins.inha.uz"):
    if location.startswith("//"):
        return "http:" + location.replace("ins.iutdev.ac.kr", base_host)
    if location.startswith("/"):
        return f"http://{base_host}{location}"
    parsed = urlparse(location)
    return urlunparse(parsed._replace(netloc=base_host))

def is_logged_in(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    if not title:
        return False
    return title.text.strip() != "IUT Portal System"

async def get_gpa_by_soup(studentId: str, password: str):
    async with SCRAPE_LIMIT:
        try:
            BASE = os.getenv("BASE")
            LOGIN_URL = os.getenv("LOGIN_URL")
            FRAMESET_URL = os.getenv("FRAMESET_URL")
            TARGET_URL = os.getenv("TARGET_URL")

            USERNAME = studentId
            PASSWORD = password

            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": LOGIN_URL,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            timeout = httpx.Timeout(10.0)
            limits = httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
            )

            async with httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                limits=limits,
                follow_redirects=False,
            ) as session:

                # 1) Load login page
                r = await session.get(LOGIN_URL)
                soup = BeautifulSoup(r.text, "html.parser")

                def hidden(name):
                    tag = soup.find("input", {"name": name})
                    return tag["value"] if tag else ""

                payload = {
                    "__VIEWSTATE": hidden("__VIEWSTATE"),
                    "__VIEWSTATEGENERATOR": hidden("__VIEWSTATEGENERATOR"),
                    "__EVENTVALIDATION": hidden("__EVENTVALIDATION"),
                    "__EVENTTARGET": "",
                    "__EVENTARGUMENT": "",
                    "txtInhaID": USERNAME.upper(),
                    "txtPW": PASSWORD,
                    "btnLogin": ""
                }

                # 2) Login
                r = await session.post(LOGIN_URL, data=payload)

                if not is_logged_in(r.text):
                    return {
                        "error": "login or password is incorrect",
                        "status_code": int(403)
                    }

                if r.status_code in (301, 302) and "Location" in r.headers:
                    await session.get(normalize_redirect(r.headers["Location"]))

                # 3) Frameset
                r = await session.get(FRAMESET_URL)
                if r.status_code in (301, 302) and "Location" in r.headers:
                    await session.get(normalize_redirect(r.headers["Location"]))

                # 4) Target page
                r = await session.get(TARGET_URL)
                if r.status_code in (301, 302) and "Location" in r.headers:
                    r = await session.get(normalize_redirect(r.headers["Location"]))

                # 5) Result
                if "dgList" in r.text:
                    soup = BeautifulSoup(r.text, "html.parser")

                    data = []

                    credits_aquired = soup.find("span", id="lblScore2").text
                    gpa_score = soup.find("span", id="lblScore3").text

                    table = soup.find("table", id="dgList")
                    rows = table.find_all("tr")[1:]

                    for row in rows:
                        cols = row.find_all("td")
                        data.append({
                            "subject": cols[2].text,
                            "credit": cols[5].text,
                            "grade": cols[6].text
                        })

                    return {
                        "status_code": 200,
                        "credits": credits_aquired,
                        "gpa_score": gpa_score,
                        "table": data
                    }

                return {
                    "error": "login or password is incorrect",
                    "status_code": int(403)
                }

        except Exception:
            return {
                "error": "login or password is incorrect",
                "status_code": int(403)
            }

async def getting_gpa_dict(studentId, password):
    return await get_gpa_by_soup(studentId, password)
