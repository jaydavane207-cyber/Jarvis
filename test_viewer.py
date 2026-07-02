from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

file_path = os.path.abspath('conversation_viewer.html')
driver.get(f'file:///{file_path.replace(os.sep, "/")}')

logs = driver.get_log('browser')
has_errors = False
for entry in logs:
    if entry['level'] == 'SEVERE':
        print(f"ERROR: {entry['message']}")
        has_errors = True
    else:
        print(f"LOG: {entry['message']}")

if not has_errors:
    print("SUCCESS: No severe console errors found on load.")

driver.quit()
