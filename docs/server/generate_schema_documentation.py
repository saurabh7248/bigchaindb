""" Script to render transaction schema into .rst document """

from collections import OrderedDict
import os.path

import yaml

from bigchaindb.common.schema import TX_SCHEMA_YAML


TPL_PROP = """\
%(title)s
%(underline)s

**type:** %(type)s

%(description)s
"""


TPL_DOC = """\
..  This file was auto generated by %(file)s

==================
Transaction Schema
==================

* `Transaction`_

* `Transaction Body`_

* Condition_

* Fulfillment_

* Asset_

* Metadata_

.. raw:: html

    <style>
    #transaction-schema h2 {
         border-top: solid 3px #6ab0de;
         background-color: #e7f2fa;
         padding: 5px;
    }
    #transaction-schema h3 {
         background: #f0f0f0;
         border-left: solid 3px #ccc;
         font-weight: bold;
         padding: 6px;
         font-size: 100%%;
         font-family: monospace;
    }
    </style>

Transaction
-----------

%(wrapper)s

Transaction Body
----------------

%(transaction)s

Condition
----------

%(condition)s

Fulfillment
-----------

%(fulfillment)s

Asset
-----

%(asset)s

Metadata
--------

%(metadata)s
"""


def ordered_load_yaml(stream):
    """ Custom YAML loader to preserve key order """
    class OrderedLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return OrderedDict(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)


TX_SCHEMA = ordered_load_yaml(TX_SCHEMA_YAML)


DEFINITION_BASE_PATH = '#/definitions/'


def render_section(section_name, obj):
    """ Render a domain object and it's properties """
    out = [obj['description']]
    for name, prop in obj.get('properties', {}).items():
        try:
            title = '%s.%s' % (section_name, name)
            out += [TPL_PROP % {
                'title': title,
                'underline': '^' * len(title),
                'description': property_description(prop),
                'type': property_type(prop),
            }]
        except Exception as exc:
            raise ValueError("Error rendering property: %s" % name, exc)
    return '\n\n'.join(out + [''])


def property_description(prop):
    """ Get description of property """
    if 'description' in prop:
        return prop['description']
    if '$ref' in prop:
        return property_description(resolve_ref(prop['$ref']))
    if 'anyOf' in prop:
        return property_description(prop['anyOf'][0])
    raise KeyError("description")


def property_type(prop):
    """ Resolve a string representing the type of a property """
    if 'type' in prop:
        if prop['type'] == 'array':
            return 'array (%s)' % property_type(prop['items'])
        return prop['type']
    if 'anyOf' in prop:
        return ' or '.join(property_type(p) for p in prop['anyOf'])
    if '$ref' in prop:
        return property_type(resolve_ref(prop['$ref']))
    raise ValueError("Could not resolve property type")


def resolve_ref(ref):
    """ Resolve definition reference """
    assert ref.startswith(DEFINITION_BASE_PATH)
    return TX_SCHEMA['definitions'][ref[len(DEFINITION_BASE_PATH):]]


def main():
    """ Main function """
    defs = TX_SCHEMA['definitions']
    doc = TPL_DOC % {
        'wrapper': render_section('Transaction', TX_SCHEMA),
        'transaction': render_section('Transaction',
                                      TX_SCHEMA['properties']['transaction']),
        'condition': render_section('Condition', defs['condition']),
        'fulfillment': render_section('Fulfillment', defs['fulfillment']),
        'asset': render_section('Asset', defs['asset']),
        'metadata': render_section('Metadata', defs['metadata']['anyOf'][0]),
        'file': os.path.basename(__file__),
    }

    path = os.path.join(os.path.dirname(__file__),
                        'source/schema/transaction.rst')

    open(path, 'w').write(doc)


if __name__ == '__main__':
    main()
