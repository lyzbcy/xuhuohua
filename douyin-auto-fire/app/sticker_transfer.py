"""Keep outgoing PNG stickers below 30,000 bytes without editing source files."""
import io
import sys

MAX_STICKER_BYTES = 30_000


def compress_png(original: bytes) -> bytes:
    if len(original) < MAX_STICKER_BYTES:
        return original

    from PIL import Image

    def encode(image):
        stream = io.BytesIO()
        image.save(stream, format="PNG", optimize=True)
        return stream.getvalue()

    with Image.open(io.BytesIO(original), formats=["PNG"]) as source:
        if getattr(source, "is_animated", False):
            raise ValueError("动图表情超过 30 KB")
        image = source.convert("RGBA")
    image.info.clear()
    image.thumbnail((384, 384), Image.Resampling.LANCZOS)
    while True:
        payload = encode(image)
        if len(payload) < MAX_STICKER_BYTES:
            return payload
        for colors in (256, 128, 64):
            payload = encode(image.quantize(colors, method=Image.Quantize.FASTOCTREE))
            if len(payload) < MAX_STICKER_BYTES:
                return payload
        size = tuple(max(1, int(n * 0.8)) for n in image.size)
        image = image.resize(size, Image.Resampling.LANCZOS)


if __name__ == "__main__":
    sys.stdout.buffer.write(compress_png(sys.stdin.buffer.read()))
