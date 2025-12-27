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

            context = await browser.new_context()
            page = await context.new_page()

            url = "http://ins.inha.uz/ITIS/Start.aspx"
            await page.goto(url, timeout=30000)

            # Login
            await page.wait_for_selector("input#txtInhaID")
            await page.fill("input#txtInhaID", studentId)

            await page.wait_for_selector("input#txtPW")
            await page.fill("input#txtPW", password)

            await page.click("input#btnLogin")

            # LEFT frame
            await page.wait_for_selector("frame[name='Left']")
            left_frame = page.frame(name="Left")

            await left_frame.wait_for_selector("a#SU_65002")
            await left_frame.click("a#SU_65002")

            await left_frame.wait_for_selector(
                "//div[@id='SideMenu']//ul[@class='depth2']//a[normalize-space()='Course Evaluation']"
            )
            await left_frame.click(
                "//div[@id='SideMenu']//ul[@class='depth2']//a[normalize-space()='Course Evaluation']"
            )

            # MAIN → ifTab frames
            await page.wait_for_selector("frame[name='Main']")
            main_frame = page.frame(name="Main")

            await main_frame.wait_for_selector("frame[name='ifTab']")
            iftab_frame = main_frame.frame(name="ifTab")

            # Grades table
            await iftab_frame.wait_for_selector("#dgList")
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

            # Credits & GPA
            credits = await iftab_frame.inner_text("span#lblScore2")
            gpa_score = await iftab_frame.inner_text("span#lblScore3")

            final_data = {
                "status_code": 200,
                "credits": credits,
                "gpa_score": gpa_score,
                "table": data,
            }

            await browser.close()
            return final_data

    except PlaywrightTimeoutError:
        return {"error": "login or password is incorrect", "status_code": 403}

    except Exception:
        return {"error": "login or password is incorrect", "status_code": 403}
