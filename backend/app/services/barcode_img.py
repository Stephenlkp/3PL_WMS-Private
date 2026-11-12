import io


def render_code128(value: str) -> bytes:
    from barcode import Code128
    from barcode.writer import ImageWriter

    buffer = io.BytesIO()
    Code128(value, writer=ImageWriter()).write(
        buffer,
        {
            "module_width": 0.25,
            "module_height": 14.0,
            "font_size": 10,
            "text_distance": 4.0,
            "quiet_zone": 2.0,
            "write_text": True,
        },
    )
    return buffer.getvalue()
