from defusedxml import ElementTree as ET
import re
def normalize_key(s):
    """Normalize string for robust matching: remove non-alnum and lowercase."""
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def parse_xml_dynamic(file_path):
    """
    Parse an XML file into nested Python structures.
    - Attributes -> '@attr'
    - Text -> '#text'
    - Repeated tags -> lists
    - Namespaces are stripped from tag names
    """
    def strip_tag(tag):
        # Convert '{ns}tag' -> 'tag' or return tag unchanged if no namespace
        return tag.split('}', 1)[-1] if '}' in tag else tag

    def element_to_dict(element):
        result = {}
        # attributes
        if element.attrib:
            for key, value in element.attrib.items():
                # keys may carry namespaces too; strip them
                result[f"@{strip_tag(key)}"] = value

        # children
        children = list(element)
        if children:
            for child in children:
                child_data = element_to_dict(child)
                tag = strip_tag(child.tag)
                if tag in result:
                    if isinstance(result[tag], list):
                        result[tag].append(child_data)
                    else:
                        result[tag] = [result[tag], child_data]
                else:
                    result[tag] = child_data

        # text content
        text = (element.text or '').strip()
        if text:
            if result:
                # element had attrs or children -> keep text under '#text'
                result['#text'] = text
            else:
                # leaf with only text -> return the text directly
                return text

        return result or None

    tree = ET.parse(file_path)
    root = tree.getroot()
    return {strip_tag(root.tag): element_to_dict(root)}

