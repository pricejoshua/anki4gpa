import os
import base64
import requests

# === CONFIGURATION ===
AUDIO_DIR = "."   # folder with 1.mp3, 2.mp3, ...
IMAGE_DIR = "."  # folder with 1.png, 2.png, ...
DECK_NAME = "farsi (laca)::session 6::Vocab"  # change this to your deck name
MODEL_NAME = "Farsi"  # or your custom note type
START, END = 1, 25    # range of numbered files
UNITSESS = "Unit_1_Session_6"

# === HELPER ===
def invoke(action, **params):
    return requests.post("http://localhost:8765", json={
        "action": action,
        "version": 6,
        "params": params
    }).json()

def store_media(path, newname):
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    result = invoke("storeMediaFile", filename=newname, data=data)
    print(f"Uploaded {path} as {newname}, result: {result}")
    return newname

def add_card(num):
    audio_file = os.path.join(AUDIO_DIR, f"{num}.mp3")
    image_file = os.path.join(IMAGE_DIR, f"{num}.png")  # adjust if .jpg

    if not os.path.exists(audio_file) or not os.path.exists(image_file):
        print(f"Skipping {num}: missing file")
        return

    # Build new audio filename with deck name
    new_audio_name = f"{UNITSESS}_{num}.mp3"
    new_image_name = f"{UNITSESS}_{num}.png"

    # Upload media with new names
    audio_name = store_media(audio_file, new_audio_name)
    image_name = store_media(image_file, new_image_name)

    # Create note (Basic model uses Front/Back fields)
    note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {
            "Audio": f"[sound:{audio_name}]",
            "Image": f"[sound:{audio_name}]<br><img src='{image_name}'>"
        },
        "options": {"allowDuplicate": False},
        "tags": ["auto"]
    }

    result = invoke("addNote", note=note)
    print(f"Added card {num}: {result}")

def main():
    for i in range(START, END + 1):
        add_card(i)

if __name__ == "__main__":
    main()
