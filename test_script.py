from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

options = Options()
options.add_argument('--headless')
# options.add_argument('--autoplay-policy=no-user-gesture-required') # I won't use this, so we test real autoplay behavior
driver = webdriver.Chrome(options=options)

driver.get('http://jarvis:admin123@127.0.0.1:8000/chat')
time.sleep(2)

# use real selenium click
btn = driver.find_element(By.ID, 'jay-voice-btn')
btn.click()
time.sleep(1)

opt = driver.find_element(By.CSS_SELECTOR, '.voice-selector-option')
opt.click()
time.sleep(3)

for entry in driver.get_log('browser'):
    print(entry)
driver.quit()
