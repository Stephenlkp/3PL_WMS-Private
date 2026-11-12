"""Opening warehouse: StarLinks Logistics, one customer (iSpring), stock from the SKU list.

Run with `python -m app.seed`. Safe to run again; it stops if the admin exists.
"""

from __future__ import annotations

import io
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User
from app.schemas import CustomerIn, LocationIn, ProductIn, ReceiveIn, UserCreate
from app.services import catalog, files, stock

STOCK_FILE = Path(__file__).resolve().parents[1] / "data" / "iSpring_SKU_List.xlsx"
FEATURED_SKU = "MRO400EU"
FEATURED_BIN = "A-02-03"

PASSWORD = "Wms-demo-123"


def load_opening_stock() -> list[tuple[str, int]]:
    """Each spreadsheet row is one unit. Repeated SKUs add up. The # column is only a line number."""
    import openpyxl

    workbook = openpyxl.load_workbook(STOCK_FILE, data_only=True, read_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    header = [str(cell).strip().upper() if cell is not None else "" for cell in rows[0]]
    sku_index = header.index("SKU")
    counts: Counter[str] = Counter()
    order: list[str] = []
    for row in rows[1:]:
        raw = row[sku_index] if row and len(row) > sku_index else None
        if raw is None or not str(raw).strip():
            continue
        sku = str(raw).strip()
        if sku not in counts:
            order.append(sku)
        counts[sku] += 1
    return [(sku, counts[sku]) for sku in order]


def _font(size: int):
    from PIL import ImageFont

    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _image(title: str, subtitle: str, kind: str) -> bytes:
    image = Image.new("RGB", (900, 520), "#243044" if kind == "rack" else "#f6f1e7")
    draw = ImageDraw.Draw(image)
    ink = "#f6f1e7" if kind == "rack" else "#1c1915"
    accent = "#c9841a"
    if kind == "rack":
        draw.rectangle((36, 36, 864, 484), outline=accent, width=8)
        for top in (130, 250, 370):
            draw.rectangle((72, top, 500, top + 88), outline=ink, width=4)
            draw.line((72, top + 44, 500, top + 44), fill="#8aa0b8", width=2)
        draw.rounded_rectangle((540, 130, 820, 458), radius=16, fill="#1c1915", outline=accent, width=6)
        draw.text((580, 180), "A02", fill=accent, font=_font(78))
        draw.text((600, 280), "03", fill=ink, font=_font(78))
        draw.text((72, 52), title, fill=ink, font=_font(42))
    else:
        draw.rectangle((28, 28, 872, 492), outline=ink, width=4)
        draw.text((56, 70), title, fill=ink, font=_font(48))
        draw.text((56, 150), subtitle, fill=ink, font=_font(28))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG" if kind == "rack" else "JPEG", quality=90)
    return buffer.getvalue()


def run() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == "admin@wms.local")):
            print("Seed already present")
            return
        admin = User(
            email="admin@wms.local",
            password_hash=hash_password(PASSWORD),
            full_name="Amina Shah",
            role="admin",
            active=True,
        )
        db.add(admin)
        db.flush()

        def user(email: str, name: str, role: str, customer_id=None) -> User:
            created = catalog.create_user(
                db,
                admin,
                UserCreate(email=email, password=PASSWORD, full_name=name, role=role, customer_id=customer_id),
                None,
            )
            return created

        customer = catalog.create_customer(db, admin, CustomerIn(code="ISPR", name="iSpring"), None)
        supervisor = user("supervisor@wms.local", "Ben Ortiz", "warehouse_supervisor")
        picker = user("picker@wms.local", "Priya Tan", "picker")
        user("packer@wms.local", "Leo Marsh", "packer")
        user("ispring@wms.local", "iSpring", "customer", customer.id)

        locations = {}
        codes: list[str] = []
        for zone in ("A", "B"):
            for rack in ("01", "02", "03"):
                for level in ("01", "02", "03"):
                    code = f"{zone}-{rack}-{level}"
                    codes.append(code)
                    locations[code] = catalog.create_location(db, supervisor, LocationIn(location_code=code), None)

        photo = files.store_bytes(
            db,
            supervisor,
            filename="rack-a-02-03.png",
            declared_type="image/png",
            data=_image("RACK A02-03", "Zone A · Rack 02 · Level 03", "rack"),
            customer_id=None,
            ip=None,
        )
        locations[FEATURED_BIN].photo_file_id = photo.id

        opening = load_opening_stock()
        other_bins = [code for code in codes if code != FEATURED_BIN]
        placed: dict[str, list[tuple[str, int]]] = {code: [] for code in codes}
        cursor = 0
        for sku, quantity in opening:
            created = catalog.create_product(
                db,
                supervisor,
                ProductIn(customer_id=customer.id, sku=sku, name=sku, description="iSpring"),
                None,
            )
            bin_code = FEATURED_BIN if sku == FEATURED_SKU else other_bins[cursor % len(other_bins)]
            if sku != FEATURED_SKU:
                cursor += 1
            placed[bin_code].append((created.barcode, quantity))

        for code, lines in placed.items():
            if not lines:
                continue
            stock.receive(
                db,
                picker,
                ReceiveIn(
                    customer_id=customer.id,
                    location_id=locations[code].id,
                    notes="Opening stock from iSpring SKU list",
                    lines=[{"barcode": barcode, "quantity": quantity} for barcode, quantity in lines],
                ),
                None,
            )

        featured_qty = next(quantity for sku, quantity in opening if sku == FEATURED_SKU)
        db.commit()
        print("Seeded iSpring opening stock")
        print(f"{len(opening)} SKUs, {sum(quantity for _, quantity in opening)} units")
        print("Password for every account: Wms-demo-123")
        print("admin@wms.local  supervisor@wms.local  picker@wms.local  packer@wms.local")
        print("ispring@wms.local")
        print(f"{FEATURED_SKU} is at {FEATURED_BIN} with {featured_qty} on hand")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
