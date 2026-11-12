from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.tenant import scoped_customer_id
from app.domain.enums import Role
from app.models.entities import Location, Order, Product, Shipment, User
from app.schemas import SearchHit, SearchOut
from app.services.queries import balance_rows


def search(session: Session, user: User, q: str) -> SearchOut:
    term = q.strip()[:80]
    if not term:
        return SearchOut(query="", hits=[])
    like = f"%{term}%"
    hits: list[SearchHit] = []
    scoped = scoped_customer_id(user, None)

    for row in balance_rows(session, user, customer_id=scoped, q=term, view="location", low_stock=False):
        if len(hits) >= 20:
            break
        hits.append(
            SearchHit(
                kind="inventory",
                label=row.sku,
                detail=row.product_name,
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                product_id=row.product_id,
                sku=row.sku,
                barcode=row.barcode,
                location_code=row.location_code,
                on_hand_qty=row.location_qty if row.location_qty is not None else row.on_hand_qty,
                reserved_qty=row.reserved_qty,
                available_qty=row.available_qty,
            )
        )

    product_stmt = select(Product).where(or_(Product.sku.ilike(like), Product.name.ilike(like), Product.barcode.ilike(like)))
    if scoped is not None:
        product_stmt = product_stmt.where(Product.customer_id == scoped)
    seen_products = {hit.product_id for hit in hits}
    for product in session.scalars(product_stmt.limit(10)).all():
        if product.id in seen_products:
            continue
        hits.append(
            SearchHit(
                kind="product",
                label=product.sku,
                detail=product.name,
                customer_id=product.customer_id,
                customer_name=product.customer.name,
                product_id=product.id,
                sku=product.sku,
                barcode=product.barcode,
                on_hand_qty=0,
                reserved_qty=0,
                available_qty=0,
            )
        )

    if user.role != Role.CUSTOMER:
        for location in session.scalars(select(Location).where(Location.location_code.ilike(like)).limit(8)).all():
            hits.append(
                SearchHit(
                    kind="location",
                    label=location.location_code,
                    detail=f"Zone {location.zone} rack {location.rack} level {location.level}",
                    location_code=location.location_code,
                )
            )

    order_stmt = select(Order).where(or_(Order.order_number.ilike(like), Order.tracking_number.ilike(like)))
    if scoped is not None:
        order_stmt = order_stmt.where(Order.customer_id == scoped)
    for order in session.scalars(order_stmt.limit(8)).all():
        hits.append(
            SearchHit(
                kind="order",
                label=order.order_number,
                detail=order.status,
                customer_id=order.customer_id,
                customer_name=order.customer.name,
                order_id=order.id,
                order_number=order.order_number,
                tracking_number=order.tracking_number,
            )
        )

    ship_stmt = select(Shipment).where(Shipment.tracking_number.ilike(like))
    if scoped is not None:
        ship_stmt = ship_stmt.where(Shipment.customer_id == scoped)
    for shipment in session.scalars(ship_stmt.limit(8)).all():
        hits.append(
            SearchHit(
                kind="shipment",
                label=shipment.shipment_number,
                detail=shipment.status,
                customer_id=shipment.customer_id,
                tracking_number=shipment.tracking_number,
                order_id=shipment.order_id,
            )
        )
    return SearchOut(query=term, hits=hits[:40])
