import io


def render_label(value: str, style: str = "code128") -> bytes:
    if style == "qr":
        return render_qr(value)
    return render_code128(value)


def render_qr(value: str) -> bytes:
    import qrcode

    image = qrcode.make(value, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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
