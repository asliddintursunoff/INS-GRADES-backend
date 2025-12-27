import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

class LoginFailedError(Exception):
    pass


async def getting_gpa_dict(studentId: str, password: str):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--lang=en-US,en",
                ],
            )

            context = await browser.new_context(
                locale="en-US",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            page = await context.new_page()

            # IMPORTANT: handle JS alerts (Selenium did this implicitly)
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

            url = "http://ins.inha.uz/ITIS/Start.aspx"
            await page.goto(url, timeout=30000)

            # === LOGIN (same as Selenium) ===
            await page.wait_for_selector("input#txtInhaID", timeout=15000)
            await page.fill("input#txtInhaID", studentId)

            await page.wait_for_selector("input#txtPW", timeout=15000)
            await page.fill("input#txtPW", password)

            await page.wait_for_selector("input#btnLogin", timeout=15000)
            await page.click("input#btnLogin")

            # === WAIT FOR LOGIN SUCCESS ===
            # Selenium: frame_to_be_available_and_switch_to_it("Left")
            try:
                await page.wait_for_selector("frame[name='Left']", timeout=20000)
            except PlaywrightTimeoutError:
                raise LoginFailedError()

            # === LEFT FRAME ===
            left_frame = page.frame(name="Left")
            if not left_frame:
                raise LoginFailedError()

            await left_frame.wait_for_selector("a#SU_65002", timeout=15000)
            await left_frame.click("a#SU_65002")

            await left_frame.wait_for_selector(
                "//div[@id='SideMenu']//ul[@class='depth2']//a[normalize-space()='Course Evaluation']",
                timeout=15000,
            )
            await left_frame.click(
                "//div[@id='SideMenu']//ul[@class='depth2']//a[normalize-space()='Course Evaluation']"
            )

            # === MAIN FRAME ===
            await page.wait_for_selector("frame[name='Main']", timeout=15000)
            main_frame = page.frame(name="Main")
            if not main_frame:
                raise LoginFailedError()

            await main_frame.wait_for_selector("frame[name='ifTab']", timeout=15000)
            iftab_frame = main_frame.frame(name="ifTab")
            if not iftab_frame:
                raise LoginFailedError()

            # === GRADES TABLE ===
            await iftab_frame.wait_for_selector("#dgList", timeout=20000)
            rows = await iftab_frame.query_selector_all("#dgList tr")

            result = []
            for row in rows[1:]:
                cols = await row.query_selector_all("td")
                row_data = [await col.inner_text() for col in cols]
                result.append(row_data)

            data = []
            for j in result:
                data.append(
                    {
                        "subject": j[2],
                        "credit": j[5],
                        "grade": j[6],
                    }
                )

            # === CREDITS & GPA ===
            credits = await iftab_frame.inner_text("span#lblScore2")
            gpa_score = await iftab_frame.inner_text("span#lblScore3")

            await browser.close()

            return {
                "status_code": 200,
                "credits": credits,
                "gpa_score": gpa_score,
                "table": data,
            }

    except LoginFailedError:
        return {"error": "login or password is incorrect", "status_code": 403}

    except PlaywrightTimeoutError:
        return {"error": "login or password is incorrect", "status_code": 403}

    except Exception:
        return {"error": "login or password is incorrect", "status_code": 403}
