"""
dataforge_xml.py
────────────────
Shared XML parsing helpers for DataForge entity files.

All functions operate on xml.etree.ElementTree.Element instances from unforge-
extracted DataForge cache directories.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def find(root: ET.Element, tag: str) -> ET.Element | None:
    """Find first element with the given tag anywhere in the tree.

    Args:
        root: Root element to search from
        tag: Tag name to search for

    Returns:
        First matching element, or None if not found
    """
    return root.find(f".//{tag}")


def attr(root: ET.Element, tag: str, attr_name: str, default=None):
    """Find an element by tag and return one of its attributes.

    Args:
        root: Root element to search from
        tag: Tag name to search for
        attr_name: Attribute name to retrieve
        default: Default value if element or attribute not found

    Returns:
        Attribute value, or default if element/attribute not found
    """
    el = find(root, tag)
    return el.get(attr_name, default) if el is not None else default


def find_by_type(root: ET.Element, type_name: str) -> ET.Element | None:
    """Find first element matching *type_name* by either __type attribute or tag.

    Handles both old DataForge format (``__type`` attribute) and newer unforge
    builds (type as element tag).

    Args:
        root: Root element to search from
        type_name: Type name to match against __type attribute or tag

    Returns:
        First matching element, or None if not found
    """
    for el in root.iter():
        if el.get("__type") == type_name or el.tag == type_name:
            return el
    return None


def resource_amount(amount_el: ET.Element) -> str | None:
    """Extract the numeric value from a resourceAmountPerSecond element.

    Args:
        amount_el: Resource amount element to parse

    Returns:
        Resource amount as string, or None if not found
    """
    unit = amount_el.find(".//SPowerSegmentResourceUnit")
    if unit is not None:
        return unit.get("units")
    std = amount_el.find(".//SStandardResourceUnit")
    if std is not None:
        return std.get("standardResourceUnits")
    micro = amount_el.find(".//SMicroResourceUnit")
    if micro is not None:
        return micro.get("microResourceUnits")
    return None


def find_resource(root: ET.Element, resource: str) -> str | None:
    """Find the amount/s for a given resource anywhere in the resource network.

    Searches Generation, Conversion, and Consumption delta types. For Conversion
    deltas, checks both consumption and generation children.

    Args:
        root: Root element to search from
        resource: Resource type to search for (e.g. "Power")

    Returns:
        Resource amount as string, or None if not found
    """
    for delta_type in ("ItemResourceDeltaGeneration", "ItemResourceDeltaConversion", "ItemResourceDeltaConsumption"):
        for delta in root.iter(delta_type):
            for child in delta:
                if child.get("resource") == resource:
                    val = resource_amount(child)
                    if val is not None:
                        return val
    return None


def poly_type(elem: ET.Element) -> str:
    """Return the effective polymorphic type of a DataForge element.

    Historically CIG/unforge emitted elements like
    ``<CraftingProcess_Base __polymorphicType="CraftingProcess_Creation" ... />``
    and the generator filtered on the attribute. Newer unforge builds drop
    ``__type``/``__polymorphicType`` entirely and emit the concrete type as
    the element tag itself (``<CraftingProcess_Creation ... />``).

    Args:
        elem: Element to get type from

    Returns:
        Polymorphic type name from __polymorphicType attribute or tag
    """
    return elem.get("__polymorphicType") or elem.tag
