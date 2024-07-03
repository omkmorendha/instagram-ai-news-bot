import os
import requests
from bs4 import BeautifulSoup
import openai
import psycopg2
from dotenv import load_dotenv
from instagrapi import Client
from PIL import Image
from io import BytesIO
from datetime import datetime

load_dotenv()

feeds = ["https://www.artificialintelligence-news.com/feed/"]

DATABASE = {
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT"),
}


def connect_db():
    try:
        conn = psycopg2.connect(**DATABASE)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None


def create_table():
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    feed TEXT,
                    title TEXT,
                    caption TEXT,
                    script TEXT,
                    image_url TEXT,
                    datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (title)
                )
                """
            )
            conn.commit()

            cursor.execute("SELECT to_regclass('public.posts');")
            table_exists = cursor.fetchone()[0]

            if table_exists:
                print("posts table already exists")
            else:
                print("post table successfully created")

    except Exception as e:
        print(f"Error creating posts table in the database: {e}")

    finally:
        cursor.close()
        conn.close()


def save_post(feed, title, caption, script, image_url):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO posts (feed, title, caption, script, image_url, datetime)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (title) DO NOTHING
                """,
                (feed, title[:30], caption, script, image_url, datetime.now()),
            )
            conn.commit()

            print("Saved post to database successfully")
        except Exception as e:
            print(f"Error saving post to database: {e}")
        finally:
            cursor.close()
            conn.close()


def post_exists(title):
    conn = connect_db()
    exists = False

    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posts WHERE title = %s", (title[:30],))
        exists = cursor.fetchone() is not None
        cursor.close()
        conn.close()

    return exists


def get_rss_data(feeds):
    output = []
    for url in feeds:
        try:
            resp = requests.get(url)
            soup = BeautifulSoup(resp.text, "xml")
            for entry in soup.find_all("item"):
                item = {
                    "title": entry.find("title").text,
                    "pubdate": e.text if (e := entry.find("pubDate")) else None,
                    "content": entry.find("description").text,
                    "link": entry.find("link").text,
                }
                output.append(item)
        except Exception as e:
            print(f"Failed to scrape data for feed {url}, due to {e}")

    return output


def generate_gpt(title, content):
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
            model="dall-e-3", prompt=prompt, n=1, size="1024x1024"
        )

        image_url = response.data[0].url
        return image_url
    except Exception as e:
        print(f"Error generating image: {e}")
        return None


def download_image_as_jpg(image_url, folder="images/"):
    if not os.path.exists(folder):
        os.makedirs(folder)
    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content))
    local_filename = os.path.join(
        folder, os.path.splitext(image_url.split("/")[-1])[0] + ".jpg"
    )
    image = image.convert("RGB")
    image.save(local_filename, "JPEG")
    return local_filename


def upload_post(image_url, caption):
    try:
        image_path = download_image_as_jpg(image_url)

        USERNAME = os.getenv("INSTAGRAM_USERNAME")
        PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
        cl = Client()
        cl.login(USERNAME, PASSWORD)
        media = cl.photo_upload(path=image_path, caption=caption)
        print(f"Post successfully added: {media}")
        os.remove(image_path)
    except Exception as e:
        print(f"Error uploading post on Instagram: {e}")
        if os.path.exists(image_path):
            os.remove(image_path)


def main():
    output = get_rss_data(feeds)

    create_table()

    for out in output:
        title = out["title"]

        if not post_exists(title):
            gpt_answer = generate_gpt(title, out["content"])

            if gpt_answer:
                caption = gpt_answer.get("caption")
                script = gpt_answer.get("script")

                if caption:
                    image_url = generate_image(caption)

                    if image_url:
                        upload_post(image_url, caption)
                        save_post(feeds[0], title, caption, script, image_url)
                        break
        else:
            print(f"Post already exists: {title}")


if __name__ == "__main__":
    main()
