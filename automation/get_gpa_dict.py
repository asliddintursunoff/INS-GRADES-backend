from selenium import webdriver
from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import UnexpectedAlertPresentException

class LoginFailedError(Exception):
    pass
def _selenium_getting_gpa_dict(studentId:str,password:str):
    

    try:
        options = webdriver.ChromeOptions()
      
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=en-US,en")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)



        driver = webdriver.Chrome(options=options)
        #for waiting
        wait = WebDriverWait(driver,30)
        url = "http://ins.inha.uz/ITIS/Start.aspx"

        driver.get(url)

        input_login_field = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR,'input[id=txtInhaID]'))
            )

        input_login_field.send_keys(studentId)

        input_password_field = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR,'input[id=txtPW]'))
            )
        input_password_field.send_keys(password)


        login_btn = wait.until(
            EC.presence_of_element_located((By.XPATH,"//input[@id='btnLogin']"))
            )
        login_btn.click()





        driver.switch_to.default_content()

        # 2. Switch to LEFT menu frame
        wait.until(EC.frame_to_be_available_and_switch_to_it("Left"))


        courses_btn = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR,"a[id=SU_65002]"))
            )
        courses_btn.click()

        course_evaulation = wait.until(
            EC.presence_of_element_located((By.XPATH,"//div[@id='SideMenu']//ul[@class='depth2']//a[normalize-space()='Course Evaluation']"))
        )
        course_evaulation.click()

        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it("Main"))

        wait.until(EC.frame_to_be_available_and_switch_to_it("ifTab"))


        grades_table = wait.until(
            EC.presence_of_element_located((By.ID,'dgList'))
        )

        table = grades_table.find_elements(By.CSS_SELECTOR, 'tr')



        result = []

        # result.append([headers.text for headers in table[0].find_elements(By.CSS_SELECTOR,"th")])



        for t in table[1:]:
            lst = []
            for info in t.find_elements(By.TAG_NAME,"td"):
                lst.append(info.text)
            result.append(lst)


        data = []
        for j in result:
            data.append({"subject":j[2],"credit":j[5],"grade":j[6]})


        #for getting credits
        credits = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR,"span[id='lblScore2']"))

        ).text

        gpa_score = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR,"span[id='lblScore3']"))
        ).text

        final_data = {
            "status_code":200,
            "credits":credits,
            "gpa_score":gpa_score,
            "table":data
        }
        driver.quit()

        return final_data

    except UnexpectedAlertPresentException as e:
        return {'error':"login or password is incorrect","status_code":int(403)}

import asyncio

selenium_lock = asyncio.Semaphore(1)

async def getting_gpa_dict(studentId: str, password: str):
    async with selenium_lock:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            _selenium_getting_gpa_dict,
            studentId,
            password,
        )

