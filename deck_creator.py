"""
Anki deck creation from paired audio/image files
Based on Auto.py - creates .apkg files for import into Anki
"""

import os
import genanki
import random


def create_anki_deck(paired_files, media_dir, deck_name="Vocabulary Deck",
                     model_name="Vocabulary", tags=None, unit_session=""):
    """
    Create an Anki deck (.apkg) from paired audio and image files.

    Args:
        paired_files: List of tuples (number, audio_path, image_path)
        media_dir: Directory containing the media files
        deck_name: Name of the Anki deck
        model_name: Name of the note type
        tags: List of tags to add to each card
        unit_session: Prefix for card numbers (e.g., "Unit_1_Session_1")

    Returns:
        Path to the created .apkg file
    """

    if tags is None:
        tags = []

    # Generate random IDs for deck and model
    deck_id = random.randrange(1 << 30, 1 << 31)
    model_id = random.randrange(1 << 30, 1 << 31)

    # Create Anki model (note type)
    my_model = genanki.Model(
        model_id,
        model_name,
        fields=[
            {'name': 'Number'},
            {'name': 'Audio'},
            {'name': 'Image'},
        ],
        templates=[
            {
                'name': 'Card',
                'qfmt': '{{Audio}}<br>{{Image}}',
                'afmt': '{{FrontSide}}<hr id="answer">{{Number}}',
            },
        ],
        css="""
        .card {
            font-family: arial;
            font-size: 20px;
            text-align: center;
            color: black;
            background-color: white;
        }
        img {
            max-width: 90%;
            max-height: 400px;
        }
        """
    )

    # Create deck
    my_deck = genanki.Deck(deck_id, deck_name)

    # Add notes for each paired file
    media_files = []

    for number, audio_path, image_path in paired_files:
        audio_filename = os.path.basename(audio_path)
        image_filename = os.path.basename(image_path)

        # Add to media files list
        media_files.append(audio_path)
        media_files.append(image_path)

        # Create note
        note = genanki.Note(
            model=my_model,
            fields=[
                f"{unit_session}_{number}" if unit_session else str(number),
                f"[sound:{audio_filename}]",
                f'<img src="{image_filename}">'
            ],
            tags=tags
        )

        my_deck.add_note(note)

    # Create package
    my_package = genanki.Package(my_deck)
    my_package.media_files = media_files

    # Save .apkg file
    output_path = os.path.join(media_dir, f"{deck_name.replace(' ', '_')}.apkg")
    my_package.write_to_file(output_path)

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python deck_creator.py <media_dir> <deck_name> [tags]")
        print("\nThe media_dir should contain paired files: 1.png, 1.mp3, 2.png, 2.mp3, etc.")
        print("\nExample:")
        print("  python deck_creator.py output/ \"My Vocabulary\" vocab,unit1")
        sys.exit(1)

    media_dir = sys.argv[1]
    deck_name = sys.argv[2]
    tags = sys.argv[3].split(',') if len(sys.argv) > 3 else []

    print(f"Media directory: {media_dir}")
    print(f"Deck name: {deck_name}")
    print(f"Tags: {tags}")
    print("-" * 50)

    # Find paired files in the directory
    files = os.listdir(media_dir)
    audio_files = {f for f in files if f.endswith('.mp3')}
    image_files = {f for f in files if f.endswith('.png')}

    # Extract numbers and pair
    paired_files = []
    for audio_file in sorted(audio_files):
        # Extract number from filename
        import re
        match = re.search(r'(\d+)', audio_file)
        if match:
            number = match.group(1)
            image_file = f"{number}.png"

            if image_file in image_files:
                audio_path = os.path.join(media_dir, audio_file)
                image_path = os.path.join(media_dir, image_file)
                paired_files.append((number, audio_path, image_path))

    print(f"Found {len(paired_files)} paired files")

    if not paired_files:
        print("ERROR: No paired files found!")
        print("Make sure the directory contains matching numbered files: 1.png/1.mp3, 2.png/2.mp3, etc.")
        sys.exit(1)

    # Create deck
    output_path = create_anki_deck(
        paired_files,
        media_dir,
        deck_name=deck_name,
        model_name="Vocabulary",
        tags=tags,
        unit_session=""
    )

    print(f"\nDeck created successfully!")
    print(f"Output file: {output_path}")
    print(f"Cards in deck: {len(paired_files)}")
    print("\nImport this .apkg file into Anki (File > Import)")
