"""
Media Editor Module - Edit extracted audio clips and images
Provides functionality to trim, delete, rename, and reorder media files
"""

import os
import shutil
from pydub import AudioSegment
from PIL import Image


# ============================================================================
# AUDIO EDITING FUNCTIONS
# ============================================================================

def trim_audio_clip(audio_path, start_ms, end_ms, output_path=None):
    """
    Trim an audio clip to specified start and end times.

    Args:
        audio_path (str): Path to the audio file
        start_ms (int): Start time in milliseconds
        end_ms (int): End time in milliseconds
        output_path (str): Output path (if None, overwrites original)

    Returns:
        str: Path to the trimmed audio file
    """
    audio = AudioSegment.from_mp3(audio_path)

    # Validate times
    duration = len(audio)
    start_ms = max(0, start_ms)
    end_ms = min(duration, end_ms)

    if start_ms >= end_ms:
        raise ValueError(f"Invalid trim range: start ({start_ms}ms) >= end ({end_ms}ms)")

    # Trim audio
    trimmed = audio[start_ms:end_ms]

    # Save
    if output_path is None:
        output_path = audio_path

    trimmed.export(output_path, format="mp3")
    return output_path


def delete_audio_clip(audio_path):
    """
    Delete an audio clip file.

    Args:
        audio_path (str): Path to the audio file to delete

    Returns:
        bool: True if successful
    """
    if os.path.exists(audio_path):
        os.remove(audio_path)
        return True
    return False


def get_audio_duration(audio_path):
    """
    Get the duration of an audio file in milliseconds.

    Args:
        audio_path (str): Path to the audio file

    Returns:
        int: Duration in milliseconds
    """
    audio = AudioSegment.from_mp3(audio_path)
    return len(audio)


def rename_audio_clip(audio_path, new_number):
    """
    Rename an audio clip to a new number.

    Args:
        audio_path (str): Path to the current audio file
        new_number (int): New number for the file

    Returns:
        str: Path to the renamed file
    """
    directory = os.path.dirname(audio_path)
    extension = os.path.splitext(audio_path)[1]
    new_path = os.path.join(directory, f"{new_number}{extension}")

    # If target exists, add occurrence suffix
    if os.path.exists(new_path):
        counter = 2
        while os.path.exists(os.path.join(directory, f"{new_number}_{counter}{extension}")):
            counter += 1
        new_path = os.path.join(directory, f"{new_number}_{counter}{extension}")

    shutil.move(audio_path, new_path)
    return new_path


# ============================================================================
# IMAGE EDITING FUNCTIONS
# ============================================================================

def delete_image(image_path):
    """
    Delete an image file.

    Args:
        image_path (str): Path to the image file to delete

    Returns:
        bool: True if successful
    """
    if os.path.exists(image_path):
        os.remove(image_path)
        return True
    return False


def rename_image(image_path, new_number):
    """
    Rename an image to a new number.

    Args:
        image_path (str): Path to the current image file
        new_number (int): New number for the file

    Returns:
        str: Path to the renamed file
    """
    directory = os.path.dirname(image_path)
    extension = os.path.splitext(image_path)[1]
    new_path = os.path.join(directory, f"{new_number}{extension}")

    # If target exists, add occurrence suffix
    if os.path.exists(new_path):
        counter = 2
        while os.path.exists(os.path.join(directory, f"{new_number}_{counter}{extension}")):
            counter += 1
        new_path = os.path.join(directory, f"{new_number}_{counter}{extension}")

    shutil.move(image_path, new_path)
    return new_path


def reorder_images(image_dir, new_order):
    """
    Reorder images based on a new ordering.

    Args:
        image_dir (str): Directory containing images
        new_order (list): List of (old_filename, new_number) tuples

    Returns:
        list: New filenames after reordering
    """
    # Create temporary directory for safe renaming
    temp_dir = os.path.join(image_dir, "_temp_reorder")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # First, move all files to temp directory with new names
        temp_files = []
        for old_filename, new_number in new_order:
            old_path = os.path.join(image_dir, old_filename)
            if os.path.exists(old_path):
                extension = os.path.splitext(old_filename)[1]
                temp_filename = f"{new_number}{extension}"
                temp_path = os.path.join(temp_dir, temp_filename)
                shutil.copy2(old_path, temp_path)
                temp_files.append(temp_filename)

        # Delete original files
        for old_filename, _ in new_order:
            old_path = os.path.join(image_dir, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)

        # Move files from temp back to original directory
        new_filenames = []
        for temp_filename in temp_files:
            temp_path = os.path.join(temp_dir, temp_filename)
            final_path = os.path.join(image_dir, temp_filename)
            shutil.move(temp_path, final_path)
            new_filenames.append(temp_filename)

        return new_filenames

    finally:
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def get_image_info(image_path):
    """
    Get information about an image file.

    Args:
        image_path (str): Path to the image file

    Returns:
        dict: Image information (size, format, dimensions)
    """
    img = Image.open(image_path)
    file_size = os.path.getsize(image_path)

    return {
        'format': img.format,
        'mode': img.mode,
        'size': img.size,  # (width, height)
        'file_size_kb': file_size / 1024
    }


# ============================================================================
# BATCH OPERATIONS
# ============================================================================

def batch_delete_media(file_paths):
    """
    Delete multiple media files at once.

    Args:
        file_paths (list): List of file paths to delete

    Returns:
        dict: Results with counts of deleted and failed files
    """
    deleted = []
    failed = []

    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted.append(path)
            else:
                failed.append((path, "File not found"))
        except Exception as e:
            failed.append((path, str(e)))

    return {
        'deleted': deleted,
        'failed': failed,
        'count_deleted': len(deleted),
        'count_failed': len(failed)
    }


def batch_rename_media(rename_list):
    """
    Rename multiple media files at once.

    Args:
        rename_list (list): List of (old_path, new_number) tuples

    Returns:
        dict: Results with renamed files and any failures
    """
    renamed = []
    failed = []

    for old_path, new_number in rename_list:
        try:
            if os.path.exists(old_path):
                directory = os.path.dirname(old_path)
                extension = os.path.splitext(old_path)[1]
                new_filename = f"{new_number}{extension}"
                new_path = os.path.join(directory, new_filename)

                # Handle duplicates
                if os.path.exists(new_path) and new_path != old_path:
                    counter = 2
                    while os.path.exists(os.path.join(directory, f"{new_number}_{counter}{extension}")):
                        counter += 1
                    new_filename = f"{new_number}_{counter}{extension}"
                    new_path = os.path.join(directory, new_filename)

                shutil.move(old_path, new_path)
                renamed.append((old_path, new_path))
            else:
                failed.append((old_path, "File not found"))
        except Exception as e:
            failed.append((old_path, str(e)))

    return {
        'renamed': renamed,
        'failed': failed,
        'count_renamed': len(renamed),
        'count_failed': len(failed)
    }
