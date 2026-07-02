from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

driver.get('http://jarvis:admin123@127.0.0.1:8000/chat')
time.sleep(2)
for entry in driver.get_log('browser'):
    print(entry)
driver.quit()
