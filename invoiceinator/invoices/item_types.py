"""ItemType hierarchy helpers."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

from .models import ItemType


def item_type_would_cycle(item_type: ItemType | None, new_parent: ItemType | None) -> bool:
    if not new_parent:
        return False
    if item_type and item_type.pk and new_parent.pk == item_type.pk:
        return True
    ancestor = new_parent
    visited = set()
    while ancestor is not None:
        if item_type and item_type.pk and ancestor.pk == item_type.pk:
            return True
        if ancestor.pk in visited:
            break
        visited.add(ancestor.pk)
        ancestor = ancestor.parent if ancestor.parent_id else None
    return False


def validate_item_type_parent(item_type: ItemType | None, parent: ItemType | None) -> None:
    if parent is None:
        return
    if item_type and item_type.pk and parent.pk == item_type.pk:
        raise ValidationError({'parent': 'An item type cannot be its own parent.'})
    if item_type_would_cycle(item_type, parent):
        raise ValidationError({'parent': 'Parent would create a circular item type hierarchy.'})


def resolve_item_type(type_name: str | None) -> ItemType | None:
    """
    Resolve a parser or form item type string to an ``ItemType`` row.

    Supports nested paths such as ``Hardware > Screws`` or ``Hardware / Screws``.
    A plain name matches a root type first, then any type with that name.
    """
    raw = str(type_name or '').strip()
    if not raw:
        return None

    parts = [part.strip() for part in re.split(r'\s*(?:>|/)\s*', raw) if part.strip()]
    if len(parts) > 1:
        parent = None
        item_type = None
        for part in parts:
            item_type, _ = ItemType.objects.get_or_create(
                name=part,
                parent=parent,
                defaults={'description': '', 'color': '', 'icon': ''},
            )
            parent = item_type
        return item_type

    existing = ItemType.objects.filter(name=raw, parent__isnull=True).first()
    if existing:
        return existing
    existing = ItemType.objects.filter(name=raw).first()
    if existing:
        return existing
    item_type, _ = ItemType.objects.get_or_create(
        name=raw,
        parent=None,
        defaults={'description': '', 'color': '', 'icon': ''},
    )
    return item_type
