from flask import Flask, render_template, request, redirect, url_for
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import selenium.common.exceptions
from selenium.webdriver.common.keys import Keys
from dotenv import load_dotenv
import os
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from flask import jsonify
import markdown2
import threading
from selenium.webdriver.chrome.service import Service
import chromedriver_autoinstaller


app = Flask(__name__)
progress_messages = []
chromedriver_autoinstaller.install()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_tweets():
    progress_messages.clear()
    keyword = request.form['keyword']
    tweet_count = request.form['tweet_count']
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    print(start_date)
    print(end_date)

    analysis_thread = threading.Thread(target=run_analysis, args=(keyword, tweet_count, start_date, end_date))
    analysis_thread.start()

    return redirect(url_for('analysis_progress'))

def run_analysis(keyword, tweet_count, start_date, end_date):
    cookies = get_twitter_session_cookie()
    tweets = scrape_tweets_with_keyword(cookies, keyword, int(tweet_count), start_date, end_date)

    if len(tweets) == 0:
        return "No tweets found. Exiting..."

    with open("keyword.txt", "w", encoding="utf-8") as file:
        file.write(keyword)

    with open("tweets.txt", "w", encoding="utf-8") as file:
        for i, tweet in enumerate(tweets, start=1):
            file.write(f"Tweet {i}: {tweet}\n")
    
    pass_through_ai()
    

@app.route('/analysis_progress')
def analysis_progress():
    return render_template('analysis_progress.html')

@app.route('/analysis_results')
def analysis_results():
    with open("output.md", "r", encoding="utf-8") as file:
        analysis_result = file.read()
        # Convert Markdown to HTML
        analysis_result_html = markdown2.markdown(analysis_result)
    return render_template('analysis_results.html', analysis_result=analysis_result_html)

@app.route('/progress_string')
def progress_route():
    return jsonify(progress_messages)

def get_twitter_session_cookie():
    load_dotenv()
    path = os.getenv("EXECUTABLE_PATH")
    username = os.getenv("TWITTER_USERNAME")
    password = os.getenv("TWITTER_PASSWORD")
    service = Service(executable_path=path)
    options = Options()
    options.add_argument("--headless")  # Run Chrome in headless mode
    driver = webdriver.Chrome(options=options, service=service)
    driver.get('https://twitter.com/login')
    
    print("Logging into Twitter...")
    progress_messages.append("Logging into Twitter...")
    
    username_input = WebDriverWait(driver, 20).until(
        EC.visibility_of_element_located((By.XPATH, "//input[@autocomplete='username']"))
    )
    username_input.clear()
    username_input.send_keys(username)
    username_input.send_keys(Keys.ENTER)
    
    password_input = WebDriverWait(driver, 20).until(
        EC.visibility_of_element_located((By.XPATH, "//input[@name='password']"))
    )
    password_input.clear()
    password_input.send_keys(password)
    password_input.send_keys(Keys.ENTER)

    #double check logged in
    try:
        WebDriverWait(driver, 180).until(EC.url_contains("https://twitter.com/home"))
    except selenium.common.exceptions.TimeoutException:
        print("Error: Took too long to scan for login, please login and press Enter... ")
        progress_messages.append("Error: Took too long to scan for login, please login and press Enter... ")

    print("Successfully logged in to Twitter")
    progress_messages.append("Successfully logged in to Twitter")
    
    cookies = driver.get_cookies()
    driver.quit()
    session_cookies = {cookie['name']: cookie['value'] for cookie in cookies}
    return session_cookies

def scrape_tweets_with_keyword(cookies, keyword, max_tweets, start_date, end_date):
    options = Options()
    load_dotenv()
    path = os.getenv("EXECUTABLE_PATH")
    service = Service(executable_path=path)
    options.add_argument("--headless")  # Run Chrome in headless mode
    driver = webdriver.Chrome(options=options, service=service)
    
    driver.get("https://twitter.com/")
    
    print("Setting session cookies...")
    progress_messages.append("Setting session cookies...")
    # Set cookies
    for name, value in cookies.items():
        driver.add_cookie({'name': name, 'value': value})

    print("Scraping tweets...")
    progress_messages.append("Scraping tweets...")

    base_url = "https://twitter.com/search?q="
    start_datetime = datetime.strptime(start_date, "%B %d, %Y")
    end_datetime = datetime.strptime(end_date, "%B %d, %Y")
    query = f"{keyword}%20since%3A{start_datetime.strftime('%Y-%m-%d')}%20until%3A{end_datetime.strftime('%Y-%m-%d')}"
    print(query)
    url = base_url + query
    
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@data-testid='tweetText']")))
    except selenium.common.exceptions.TimeoutException:
        print("No tweets found")
        progress_messages.append("No tweets found")
        driver.quit()
        return []

    tweets = []
    tweet_divs = []
    tweets_loaded = 0
    
    while tweets_loaded < max_tweets:
        try:
            WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@data-testid='tweetText']")))
        except selenium.common.exceptions.TimeoutException:
            print("No new tweets loaded. Assuming end of page.")
            progress_messages.append("No new tweets loaded. Assuming end of page.")
            break

        # Get tweet divs
        new_tweet_divs = driver.find_elements(By.XPATH, "//div[@data-testid='tweetText']")
        
        #get rid of tweet_divs already contained in tweets
        unique_tweet_divs = [div for div in new_tweet_divs if div not in tweet_divs]
        
        
        # Check if new tweets are loaded
        if len(unique_tweet_divs) > 0:
            tweets_loaded += len(unique_tweet_divs)
            print(f"Loaded {len(unique_tweet_divs)} new tweets, with new total count {tweets_loaded}")
            progress_messages.append(f"Loaded {len(unique_tweet_divs)} new tweets, with new total count {tweets_loaded}")
            
        else:
            print("No new tweets loaded")
            progress_messages.append("No new tweets loaded")
            break
        
        tweet_divs += unique_tweet_divs
        
        for tweet_div in unique_tweet_divs:
            tweet_text = ''
            try:
                spans = tweet_div.find_elements(By.XPATH, ".//span")
                for span in spans:
                    tweet_text += span.text
                tweets.append(tweet_text.strip())
                
                driver.execute_script("arguments[0].setAttribute('data-testid', 'processed');", tweet_div)
            except selenium.common.exceptions.StaleElementReferenceException:
                print("Stale element reference. Skipping...")
                progress_messages.append("Stale element reference. Skipping...")
                continue
        

        # Break the loop if we reach the maximum number of tweets
        if tweets_loaded >= max_tweets:
            break
        
        # Scroll down to trigger loading more tweets
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    driver.quit()

    return tweets

def pass_through_ai():
    global progress_messages
    
    load_dotenv()
    api_key = os.getenv("API_KEY")
    genai.configure(api_key=api_key)
        
    model = genai.GenerativeModel('gemini-pro')

    keyword = ""

    with open("keyword.txt", "r", encoding="utf-8") as file:
        keyword = file.read()

    prompt = f"I have below a list of tweets regarding {keyword}. Analyze the tweets and come up with a list of 5 concerns people have about {keyword} and the overall consensus about {keyword}. The tweets are as follows: \n\n"

    with open("tweets.txt", "r", encoding="utf-8") as file:
        prompt += file.read()
        
    print("Analyzing tweets...")
    progress_messages.append("Analyzing tweets...")
        
    response = model.generate_content(prompt, safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
    })
    if response.prompt_feedback.block_reason != 0:
        progress_messages.append("Analysis was blocked due to the following reason: " + response.prompt_feedback.block_reason.name) # shouldn't happen but just in case
        print("Analysis was blocked due to the following reason: " + response.prompt_feedback.block_reason.name) # shouldn't happen but just in case
        return

    result = response.candidates[0].content.parts

    with open("output.md", "w", encoding="utf-8") as file:
        for part in result:
            file.write(part.text)
            file.write("\n\n")
    
    print("Analysis complete. Check output.md for the results.")
    progress_messages.append("Analysis complete. Check output.md for the results.")

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")

#TODO specify more on key points