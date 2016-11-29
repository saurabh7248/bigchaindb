""" Schema validation related functions and data """
import os.path

import jsonschema
import yaml

from bigchaindb.common.exceptions import SchemaValidationError


def _load_schema(name):
    """ Load a schema from disk """
    path = os.path.join(os.path.dirname(__file__), name + '.yaml')
    with open(path) as handle:
        return path, yaml.safe_load(handle)


def _validate_schema(schema, body):
    """ Validate data against a schema """
    try:
        jsonschema.validate(body, schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(str(exc))


TX_SCHEMA_PATH, TX_SCHEMA = _load_schema('transaction')


def validate_transaction_schema(tx):
    """ Validate a transaction dict """
    _validate_schema(TX_SCHEMA, tx)


VOTE_SCHEMA_PATH, VOTE_SCHEMA = _load_schema('vote')


def validate_vote_schema(vote):
    """ Validate a vote dict """
    # A vote does not have an ID, but the database may add one.
    if 'id' in vote:
        vote = dict(vote)
        del vote['id']
    _validate_schema(VOTE_SCHEMA, vote)
