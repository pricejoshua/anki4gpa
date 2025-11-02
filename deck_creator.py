"""
Anki deck creation from paired audio/image files
Based on Auto.py - creates .apkg files for import into Anki
"""

import os
import genanki
import hashlib


def create_anki_deck(paired_files, media_dir, deck_name="Vocabulary Deck",
                     model_name="Vocabulary", tags=None, unit_session="",
                     card_style="audio_to_image"):
    """
    Create an Anki deck (.apkg) from paired audio and image files.

    Args:
        paired_files: List of tuples (number, audio_path, image_path)
        media_dir: Directory containing the media files
        deck_name: Name of the Anki deck
        model_name: Name of the note type
        tags: List of tags to add to each card
        unit_session: Prefix for card numbers (e.g., "Unit_1_Session_1")
        card_style: Card template style:
            - "audio_to_image": Two cards - Audio→Image and Image→Audio (default)
            - "audio_only": One card - Audio on front, Image on back
            - "image_only": One card - Image on front, Audio on back
            - "both_sides": One card - Audio + Image on front, Number on back

    Returns:
        Path to the created .apkg file
    """

    if tags is None:
        tags = []

    # Generate consistent IDs using hashlib (prevents import conflicts)
    # Python's built-in hash() is salted and inconsistent across sessions

    # Use MD5 hash of deck name for deck ID
    deck_hash = hashlib.md5(deck_name.encode('utf-8')).hexdigest()
    deck_id = int(deck_hash[:8], 16)  # Use first 8 hex chars as int

    # Use MD5 hash of model name + card style for model ID
    model_hash_input = f"{model_name}_{card_style}"
    model_hash = hashlib.md5(model_hash_input.encode('utf-8')).hexdigest()
    model_id = int(model_hash[:8], 16)  # Use first 8 hex chars as int

    # Define card templates based on style
    if card_style == "audio_to_image":
        templates = [
            {
                'name': 'Sound->Image',
                'qfmt': '{{Audio}}',
                'afmt': '{{FrontSide}}<hr id="answer"><br>{{Image}}<br><small>{{Number}}</small>',
            },
            {
                'name': 'Image->Sound',
                'qfmt': '{{Image}}',
                'afmt': '{{FrontSide}}<hr id="answer"><br>{{Audio}}<br><small>{{Number}}</small>',
            },
        ]
    elif card_style == "audio_only":
        templates = [
            {
                'name': 'Sound->Image',
                'qfmt': '{{Audio}}',
                'afmt': '{{FrontSide}}<hr id="answer"><br>{{Image}}<br><small>{{Number}}</small>',
            },
        ]
    elif card_style == "image_only":
        templates = [
            {
                'name': 'Image->Sound',
                'qfmt': '{{Image}}',
                'afmt': '{{FrontSide}}<hr id="answer"><br>{{Audio}}<br><small>{{Number}}</small>',
            },
        ]
    else:  # both_sides
        templates = [
            {
                'name': 'Both->Number',
                'qfmt': '{{Audio}}<br>{{Image}}',
                'afmt': '{{FrontSide}}<hr id="answer"><br><small>{{Number}}</small>',
            },
        ]

    # Create Anki model (note type)
    my_model = genanki.Model(
        model_id,
        model_name,
        fields=[
            {'name': 'Number'},
            {'name': 'Audio'},
            {'name': 'Image'},
        ],
        templates=templates,
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
        small {
            font-size: 14px;
            color: #666;
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

        # Create note - for audio_to_image style, the note type has two templates
        # so it will automatically create both cards
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
        print("Usage: python deck_creator.py <media_dir> <deck_name> [tags] [card_style] [model_name]")
        print("\nThe media_dir should contain paired files: 1.png, 1.mp3, 2.png, 2.mp3, etc.")
        print("\nCard styles:")
        print("  audio_to_image - Two cards: Audio→Image & Image→Audio (default)")
        print("  audio_only     - One card: Audio on front, Image on back")
        print("  image_only     - One card: Image on front, Audio on back")
        print("  both_sides     - One card: Audio + Image on front")
        print("\nExamples:")
        print("  python deck_creator.py output/ \"My Vocabulary\" vocab,unit1")
        print("  python deck_creator.py output/ \"My Vocabulary\" vocab,unit1 audio_only")
        print("  python deck_creator.py output/ \"My Vocabulary\" vocab,unit1 audio_to_image VocabularyV2")
        sys.exit(1)

    media_dir = sys.argv[1]
    deck_name = sys.argv[2]
    tags = sys.argv[3].split(',') if len(sys.argv) > 3 else []
    card_style = sys.argv[4] if len(sys.argv) > 4 else "audio_to_image"
    model_name = sys.argv[5] if len(sys.argv) > 5 else "Vocabulary"

    print(f"Media directory: {media_dir}")
    print(f"Deck name: {deck_name}")
    print(f"Model name: {model_name}")
    print(f"Tags: {tags}")
    print(f"Card style: {card_style}")
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
        model_name=model_name,
        tags=tags,
        unit_session="",
        card_style=card_style
    )

    print(f"\nDeck created successfully!")
    print(f"Output file: {output_path}")

    # Calculate total cards based on style
    if card_style == "audio_to_image":
        total_cards = len(paired_files) * 2
        print(f"Cards in deck: {total_cards} ({len(paired_files)} items × 2 cards each)")
    else:
        print(f"Cards in deck: {len(paired_files)}")

    print("\nImport this .apkg file into Anki (File > Import)")
