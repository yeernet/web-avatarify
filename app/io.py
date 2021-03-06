import os
import tempfile
from io import BytesIO

import cv2
import ffmpeg
import imageio
import numpy as np
import PIL
import tensorflow as tf
from moviepy.editor import AudioFileClip
from skimage import img_as_ubyte


def write_fn(filepath, content, mode="wb"):
    with tf.io.gfile.GFile(filepath, mode) as f:
        f.write(content)


def get_video_meta_data(filepath):
    video_bytes = read_fn(filepath)

    with imageio.get_reader(video_bytes, "ffmpeg") as reader:
        return reader.get_meta_data()


def read_fn(filepath):
    with tf.io.gfile.GFile(filepath, "rb") as f:
        return f.read()


def read_image(filepath, **read_kwargs):

    buf = read_fn(filepath)
    buf = np.frombuffer(buf, np.uint8)

    arr = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if arr.ndim == 3:
        if arr.shape[-1] == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        else:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA)

    return arr


def bytes2image(image_bytes):
    with BytesIO(image_bytes) as image_bytes:
        image = PIL.Image.open(image_bytes)
        image = np.array(image, copy=True)

    return image


def image2bytes(image: np.ndarray, image_format: str = "jpeg", **save_kwargs) -> bytes:
    image = PIL.Image.fromarray(image)
    with BytesIO() as image_bytes:
        image.save(image_bytes, format=image_format, **save_kwargs)
        encoded_bytes = image_bytes.getvalue()
    return encoded_bytes


def get_frames_from_camera(camera_id):
    video_frames = []
    start_recording = False
    cap = cv2.VideoCapture(camera_id)

    # Capture initial video
    while True:
        grabbed, frame = cap.read()
        if not grabbed:
            break
        frame = frame[..., ::-1].copy()

        if start_recording:
            video_frames.append(frame.copy())
            cv2.putText(
                frame,
                "Recording",
                (20, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (209, 80, 0),
                3,
            )

        cv2.imshow("original", frame[..., ::-1])

        key = cv2.waitKey(1)

        if key == 27:  # ESC
            break
        elif key == ord("s"):
            start_recording = not start_recording

    cap.release()
    cv2.destroyAllWindows()
    return video_frames


def write_video(video_path, video_frames, fps=30):
    imageio.mimsave(
        video_path, [img_as_ubyte(frame) for frame in video_frames], fps=fps
    )


def bytes2video(videobytes, fps=30):
    with imageio.get_reader(videobytes, "ffmpeg", fps=fps) as reader:
        for image in reader:
            yield image


def get_audio_obj(video_bytes):

    with imageio.get_reader(video_bytes, "ffmpeg") as reader:
        metadata = reader.get_meta_data()

    codec = metadata["codec"]
    extension = ".mkv" if "h264" in codec else ".webm"

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_video = os.path.join(temp_dir, f"video{extension}")
        tmp_video_fixed = os.path.join(temp_dir, f"video_fixed{extension}")
        with open(tmp_video, "wb") as f:
            f.write(video_bytes)

        input_ = ffmpeg.input(tmp_video)
        # In order to get duration right, we need to use ffmpeg
        # (videos got from web dont have duration well set)
        out = ffmpeg.output(
            input_, tmp_video_fixed, vcodec="copy", acodec="copy", fflags="+genpts"
        )
        ffmpeg.run(out)

        audio = AudioFileClip(tmp_video_fixed)

    return audio


def overlay(
    background: np.ndarray, overlay, x: int, y: int,
):
    mask = overlay[..., 3]
    overlay = overlay[..., :3]

    background_width = background.shape[1]
    background_height = background.shape[0]

    h, w = overlay.shape[0], overlay.shape[1]

    if x >= background_width or y >= background_height or x + w <= 0 or y + h <= 0:
        return background[..., :3]

    if x < 0:
        w = w + x
        x = 0
        overlay = overlay[:, -w:]
        mask = mask[:, -w:]

    if y < 0:
        h = h + y
        y = 0
        overlay = overlay[-h:]
        mask = mask[-h:]

    if x + w > background_width:
        w = background_width - x
        overlay = overlay[:, :w]
        mask = mask[:, :w]

    if y + h > background_height:
        h = background_height - y
        overlay = overlay[:h]
        mask = mask[:h]

    if mask.ndim < background.ndim:
        mask = np.expand_dims(mask, axis=-1)

    if overlay.ndim < background.ndim:
        overlay = np.expand_dims(overlay, axis=-1)

    if background.ndim > 2 and background.shape[2] > 3:
        background = background[..., :3]

    background_mask = background[y : y + h, x : x + w]

    mask = mask / 255.0
    background_render = (1.0 - mask) * background_mask + mask * overlay

    background_render = background_render.astype(np.int32)
    background_render = np.clip(background_render, 0, 255).astype(np.uint8)

    background[y : y + h, x : x + w] = background_render

    return background
