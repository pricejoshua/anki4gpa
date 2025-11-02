import os
import re
import shutil
import sys
from pathlib import Path
import genanki

# Default Anki media collection folder (update as needed)
ANKI_MEDIA_FOLDER = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Anki2', 'User 1', 'collection.media')

def get_media_files(image_folder, sound_folder):
    """
    Returns a list of (image_path, sound_path, number) tuples for matching pairs.
    """
    image_files = []
    sound_files = []
    image_folder = Path(image_folder)
    sound_folder = Path(sound_folder)

    if image_folder.exists():
        image_files = list(image_folder.glob('*.jpg')) + list(image_folder.glob('*.png'))
    else:
        image_files = list(Path(ANKI_MEDIA_FOLDER).glob('*.jpg')) + list(Path(ANKI_MEDIA_FOLDER).glob('*.png'))

    if sound_folder.exists():
        sound_files = list(sound_folder.glob('*.wav'))
    else:
        sound_files = list(Path(ANKI_MEDIA_FOLDER).glob('*.wav'))


    # Map sound files by number
    sound_map = {}
    for f in sound_files:
        m = re.match(r'^(\d+)\.wav$', f.name)
        if m:
            sound_map[m.group(1)] = f
            print(m)

    pairs = []
    for img in image_files:
        print(img)
        m = re.search(r'-(\d+)(?=\.(jpg|png)$)', img.name)
        if m:
            num = m.group(1)
            print(num)
            sound = sound_map.get(num)
            if sound:
                pairs.append((img, sound, num))
    return pairs

def copy_media_files(pairs, dest_folder):
    os.makedirs(dest_folder, exist_ok=True)
    for img, snd, _ in pairs:
        shutil.copy(img, os.path.join(dest_folder, img.name))
        shutil.copy(snd, os.path.join(dest_folder, snd.name))

def create_anki_deck(pairs, output_apkg):
    deck_name = os.path.splitext(os.path.basename(output_apkg))[0]
    model = genanki.Model(
        1607392319,
        'Image-Sound Model',
        fields=[
            {'name': 'Image'},
            {'name': 'Sound'},
        ],
        templates=[
            {
                'name': 'Image->Sound',
                'qfmt': '<img src="{{Image}}">',
                'afmt': '{{FrontSide}}<br>{{Sound}}',
            },
            {
                'name': 'Sound->Image',
                'qfmt': '{{Sound}}',
                'afmt': '{{FrontSide}}<br><img src="{{Image}}">',
            },
        ],
    )
    deck = genanki.Deck(2059400110, deck_name)
    media_files = []
    for img, snd, _ in pairs:
        deck.add_note(genanki.Note(model=model, fields=[img.name, f'[sound:{snd.name}]']))
        deck.add_note(genanki.Note(model=model, fields=[img.name, f'[sound:{snd.name}]']))
        media_files.extend([str(img), str(snd)])
    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(output_apkg)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate Anki deck from image and sound pairs.')
    parser.add_argument('--images', type=str, help='Folder containing image files')
    parser.add_argument('--sounds', type=str, help='Folder containing sound files')
    parser.add_argument('--output', type=str, default='output.apkg', help='Output .apkg file')
    parser.add_argument('--media-dest', type=str, default=ANKI_MEDIA_FOLDER, help='Destination folder for used media files')
    args = parser.parse_args()

    image_folder = args.images or ANKI_MEDIA_FOLDER
    sound_folder = args.sounds or ANKI_MEDIA_FOLDER
    pairs = get_media_files(image_folder, sound_folder)
    if not pairs:
        print('No matching image/sound pairs found.')
        sys.exit(1)
    # If output is in Anki media folder, copy images and sounds there too
    output_folder = os.path.dirname(args.output)
    if os.path.normcase(output_folder) == os.path.normcase(ANKI_MEDIA_FOLDER):
        copy_media_files(pairs, ANKI_MEDIA_FOLDER)
        print(f'Media files copied to Anki media folder: {ANKI_MEDIA_FOLDER}')
    else:
        copy_media_files(pairs, args.media_dest)
        print(f'Media files copied to: {args.media_dest}')
    create_anki_deck(pairs, args.output)
    print(f'Anki deck created: {args.output}')

if __name__ == '__main__':
    main()
