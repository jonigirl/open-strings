"""Tests for src/utils/dataforge_xml.py"""

import xml.etree.ElementTree as ET

import pytest
from src.utils import dataforge_xml


@pytest.fixture
def sample_xml():
    """Sample DataForge-like XML structure for testing."""
    xml_str = """
    <root>
        <SCItemShieldGeneratorParams MaxShieldHealth="1000" MaxShieldRegen="50" />
        <nested>
            <deep>
                <SHealthComponentParams Health="500" />
            </deep>
        </nested>
        <ItemResourceDeltaGeneration>
            <resource resource="Power">
                <SStandardResourceUnit standardResourceUnits="100" />
            </resource>
        </ItemResourceDeltaGeneration>
        <ItemResourceDeltaConversion>
            <consumption resource="Heat">
                <SPowerSegmentResourceUnit units="25" />
            </consumption>
        </ItemResourceDeltaConversion>
        <CraftingProcess_Base __polymorphicType="CraftingProcess_Creation" />
        <ModernElement type="NewFormat" />
    </root>
    """
    return ET.fromstring(xml_str)


class TestFind:
    def test_find_existing_element(self, sample_xml):
        result = dataforge_xml.find(sample_xml, "SCItemShieldGeneratorParams")
        assert result is not None
        assert result.get("MaxShieldHealth") == "1000"

    def test_find_nested_element(self, sample_xml):
        result = dataforge_xml.find(sample_xml, "SHealthComponentParams")
        assert result is not None
        assert result.get("Health") == "500"

    def test_find_nonexistent_element(self, sample_xml):
        result = dataforge_xml.find(sample_xml, "NonExistent")
        assert result is None


class TestAttr:
    def test_attr_existing(self, sample_xml):
        result = dataforge_xml.attr(sample_xml, "SCItemShieldGeneratorParams", "MaxShieldHealth")
        assert result == "1000"

    def test_attr_nested(self, sample_xml):
        result = dataforge_xml.attr(sample_xml, "SHealthComponentParams", "Health")
        assert result == "500"

    def test_attr_missing_element(self, sample_xml):
        result = dataforge_xml.attr(sample_xml, "NonExistent", "attr")
        assert result is None

    def test_attr_missing_attribute(self, sample_xml):
        result = dataforge_xml.attr(sample_xml, "SCItemShieldGeneratorParams", "NonExistent")
        assert result is None

    def test_attr_with_default(self, sample_xml):
        result = dataforge_xml.attr(sample_xml, "NonExistent", "attr", default="default_value")
        assert result == "default_value"


class TestFindByType:
    def test_find_by_type_attribute(self):
        xml_str = '<root><Item __type="SCItemWeapon" name="test" /></root>'
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.find_by_type(elem, "SCItemWeapon")
        assert result is not None
        assert result.get("name") == "test"

    def test_find_by_tag_name(self, sample_xml):
        result = dataforge_xml.find_by_type(sample_xml, "ModernElement")
        assert result is not None
        assert result.get("type") == "NewFormat"

    def test_find_by_type_nonexistent(self, sample_xml):
        result = dataforge_xml.find_by_type(sample_xml, "NonExistentType")
        assert result is None


class TestResourceAmount:
    def test_resource_amount_standard(self):
        xml_str = """
        <amount>
            <SStandardResourceUnit standardResourceUnits="100" />
        </amount>
        """
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.resource_amount(elem)
        assert result == "100"

    def test_resource_amount_power_segment(self):
        xml_str = """
        <amount>
            <SPowerSegmentResourceUnit units="50" />
        </amount>
        """
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.resource_amount(elem)
        assert result == "50"

    def test_resource_amount_micro(self):
        xml_str = """
        <amount>
            <SMicroResourceUnit microResourceUnits="25" />
        </amount>
        """
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.resource_amount(elem)
        assert result == "25"

    def test_resource_amount_none(self):
        xml_str = "<amount />"
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.resource_amount(elem)
        assert result is None


class TestFindResource:
    def test_find_resource_generation(self, sample_xml):
        result = dataforge_xml.find_resource(sample_xml, "Power")
        assert result == "100"

    def test_find_resource_conversion(self, sample_xml):
        result = dataforge_xml.find_resource(sample_xml, "Heat")
        assert result == "25"

    def test_find_resource_nonexistent(self, sample_xml):
        result = dataforge_xml.find_resource(sample_xml, "Nonexistent")
        assert result is None

    def test_find_resource_consumption(self):
        xml_str = """
        <root>
            <ItemResourceDeltaConsumption>
                <resource resource="Fuel">
                    <SStandardResourceUnit standardResourceUnits="75" />
                </resource>
            </ItemResourceDeltaConsumption>
        </root>
        """
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.find_resource(elem, "Fuel")
        assert result == "75"


class TestPolyType:
    def test_poly_type_with_attribute(self):
        xml_str = '<elem __polymorphicType="ConcreteType" />'
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.poly_type(elem)
        assert result == "ConcreteType"

    def test_poly_type_without_attribute(self):
        xml_str = "<ConcreteType />"
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.poly_type(elem)
        assert result == "ConcreteType"

    def test_poly_type_prefers_attribute(self):
        xml_str = '<BaseType __polymorphicType="DerivedType" />'
        elem = ET.fromstring(xml_str)
        result = dataforge_xml.poly_type(elem)
        assert result == "DerivedType"
