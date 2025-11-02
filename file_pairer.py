"""
File pairing - matches audio clips with images by number
Based on Renaming.py - pairs files and copies them to output directory
"""

import os
import re
import shutil


def extract_number(filename):
    """Extract the number from a filename"""
    match = re.search(r'(\d+)', filename)
    return int(match.group(1)) if match else None


def pair_files(image_dir, audio_dir, output_dir):
    """
    Pair audio and image files by number.

    Args:
        image_dir: Directory containing numbered PNG images
        audio_dir: Directory containing numbered MP3 audio files
        output_dir: Directory to copy paired files to

    Returns:
        List of tuples: (number, audio_path, image_path)
    """

    os.makedirs(output_dir, exist_ok=True)

    # Get all files
    image_files = {f: f for f in os.listdir(image_dir) if f.endswith('.png')}
    audio_files = {f: f for f in os.listdir(audio_dir) if f.endswith('.mp3')}

    # Build number-to-file maps
    num_to_image = {}
    for img_file in image_files:
        num = extract_number(img_file)
        if num is not None:
            num_to_image[num] = img_file

    num_to_audio = {}
    for aud_file in audio_files:
        num = extract_number(aud_file)
        if num is not None:
            num_to_audio[num] = aud_file

    # Find all numbers that have both audio and image
    common_numbers = set(num_to_image.keys()) & set(num_to_audio.keys())

    # Copy paired files to output directory
    paired = []
    for num in sorted(common_numbers):
        img_src = os.path.join(image_dir, num_to_image[num])
        aud_src = os.path.join(audio_dir, num_to_audio[num])

        img_dst = os.path.join(output_dir, f"{num}.png")
        aud_dst = os.path.join(output_dir, f"{num}.mp3")

        shutil.copy2(img_src, img_dst)
        shutil.copy2(aud_src, aud_dst)

        paired.append((num, aud_dst, img_dst))

    return paired


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python file_pairer.py <image_dir> <audio_dir> <output_dir>")
        print("\nExample:")
        print("  python file_pairer.py images/ audio/ output/")
        sys.exit(1)

    image_dir = sys.argv[1]
    audio_dir = sys.argv[2]
    output_dir = sys.argv[3]

    print(f"Image directory: {image_dir}")
    print(f"Audio directory: {audio_dir}")
    print(f"Output directory: {output_dir}")
    print("-" * 50)

    # Get file counts
    image_files = [f for f in os.listdir(image_dir) if f.endswith('.png')]
    audio_files = [f for f in os.listdir(audio_dir) if f.endswith('.mp3')]

    print(f"Found {len(image_files)} images")
    print(f"Found {len(audio_files)} audio files")

    # Pair files
    paired = pair_files(image_dir, audio_dir, output_dir)

    print(f"\nPaired {len(paired)} files!")

    # Show which numbers are paired
    print(f"\nPaired numbers: {sorted([num for num, _, _ in paired])}")

    # Show unpaired files
    image_nums = {extract_number(f) for f in image_files if extract_number(f) is not None}
    audio_nums = {extract_number(f) for f in audio_files if extract_number(f) is not None}
    paired_nums = {num for num, _, _ in paired}

    missing_audio = image_nums - paired_nums
    missing_images = audio_nums - paired_nums

    if missing_audio:
        print(f"\nImages without matching audio: {sorted(missing_audio)}")
    if missing_images:
        print(f"Audio without matching images: {sorted(missing_images)}")

    print(f"\nFiles saved to: {output_dir}")
