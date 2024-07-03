import requests
from bs4 import BeautifulSoup
import openai
import os
from dotenv import load_dotenv
from instagrapi import Client
from PIL import Image
from io import BytesIO

load_dotenv()

def get_rss_data(feeds):
    '''
    Accepts a list of RSS Feed URLs
    And returns objects to process
    '''
    output = []
    
    for url in feeds:
        try:
            resp = requests.get(url)
            soup = BeautifulSoup(resp.text, 'xml')

            for entry in soup.find_all('item'):
                item = {
                    'title': entry.find('title').text,
                    'pubdate': e.text if(e := entry.find('pubDate')) else None,
                    'content': entry.find('description').text,
                    'link': entry.find('link').text
                }
                output.append(item)

        except Exception as e:
            print(f"Failed to scrape data for feed {url}, due to {e}")
    return output


def generate_gpt(title, content):
    """Generate an instagaram based on the content using GPT-3.5."""
    
    try:
        openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
        prompt = f"""
        Summarize the below news article into a catchy Instagram caption
        within 2000 characters, also create a script (which only contains text) that would take a TTS model about 60-90s to read.

        Based on the following content:\n\n{content}

        and 

        Title:\n\n{title}

        The answer should be in the format:
        {{
           'caption' : <caption here>,
           'script' : <script here> 
        }}
        """

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=1,
        )
        
        gpt_output = response.choices[0].message.content
        gpt_output = eval(gpt_output)
        return gpt_output
    except Exception as e:
        print(f"Error generating caption: {e}")
        return None


def generate_image(caption):
    """Generate an image using DALL-E 3 based on the provided prompt."""
    
    try:
        openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        prompt = f"""
        Create a eye-catching image for the following caption to an instagram post.
        Do not add any text to the image.
        
        Caption:\n\n{caption}
        """

        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        
        image_url = response.data[0].url
        return image_url
    except Exception as e:
        print(f"Error generating image: {e}")
        return None


def download_image_as_jpg(image_url, folder='images/'):
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content))
    local_filename = os.path.join(folder, os.path.splitext(image_url.split('/')[-1])[0] + '.jpg')

    image = image.convert('RGB')  # Ensure the image is in RGB mode
    image.save(local_filename, 'JPEG')
    return local_filename

def upload_post(image_url, caption):
    try:
        image_path = download_image_as_jpg(image_url)

        USERNAME = os.environ.get('USERNAME')
        PASSWORD = os.environ.get('PASSWORD')
        cl = Client()
        cl.login(USERNAME, PASSWORD)

        media = cl.photo_upload(path=image_path, caption=caption)
        print(f"Post successfully added: {media}")

        os.remove(image_path)
    
    except Exception as e:
        print(f"Error uploading post on Instagram: {e}")
        if os.path.exists(image_path):
            os.remove(image_path)


feeds = ['https://www.artificialintelligence-news.com/feed/']
output = get_rss_data(feeds)


for out in output:
    gpt_answer = generate_gpt(out['title'], out['content'])
    print(gpt_answer)

    if gpt_answer:
        caption = gpt_answer.get('caption')
        script = gpt_answer.get('script')

        if caption:
            image_url = generate_image(caption)
            if image_url:
                print("Image URL: ", image_url)
                upload_post(image_url, caption)
                break
            