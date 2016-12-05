from bigchaindb.common.crypto import hash_data, PublicKey, PrivateKey
from bigchaindb.common.exceptions import (InvalidHash, InvalidSignature,
                                          OperationError, DoubleSpend,
                                          TransactionDoesNotExist,
                                          TransactionNotInValidBlock,
                                          AssetIdMismatch, AmountError)
from bigchaindb.common.transaction import Transaction, Asset
from bigchaindb.common.util import gen_timestamp, serialize
from bigchaindb.common.schema import validate_transaction_schema


class Transaction(Transaction):
    def validate(self, bigchain):
        """Validate a transaction.

        Args:
            bigchain (Bigchain): an instantiated bigchaindb.Bigchain object.

        Returns:
            The transaction (Transaction) if the transaction is valid else it
            raises an exception describing the reason why the transaction is
            invalid.

        Raises:
            OperationError: if the transaction operation is not supported
            TransactionDoesNotExist: if the input of the transaction is not
                                     found
            TransactionNotInValidBlock: if the input of the transaction is not
                                        in a valid block
            TransactionOwnerError: if the new transaction is using an input it
                                   doesn't own
            DoubleSpend: if the transaction is a double spend
            InvalidHash: if the hash of the transaction is wrong
            InvalidSignature: if the signature of the transaction is wrong
        """
        if len(self.fulfillments) == 0:
            raise ValueError('Transaction contains no fulfillments')

        input_conditions = []
        inputs_defined = all([ffill.tx_input for ffill in self.fulfillments])

        if self.operation in (Transaction.CREATE, Transaction.GENESIS):
            # validate inputs
            if inputs_defined:
                raise ValueError('A CREATE operation has no inputs')
            # validate asset
            amount = sum([condition.amount for condition in self.conditions])
            self.asset.validate_asset(amount=amount)
        elif self.operation == Transaction.TRANSFER:
            if not inputs_defined:
                raise ValueError('Only `CREATE` transactions can have null '
                                 'inputs')
            # check inputs
            # store the inputs so that we can check if the asset ids match
            input_txs = []
            input_amount = 0
            for ffill in self.fulfillments:
                input_txid = ffill.tx_input.txid
                input_cid = ffill.tx_input.cid
                input_tx, status = bigchain.\
                    get_transaction(input_txid, include_status=True)

                if input_tx is None:
                    raise TransactionDoesNotExist("input `{}` doesn't exist"
                                                  .format(input_txid))

                if status != bigchain.TX_VALID:
                    raise TransactionNotInValidBlock(
                        'input `{}` does not exist in a valid block'.format(
                            input_txid))

                spent = bigchain.get_spent(input_txid, ffill.tx_input.cid)
                if spent and spent.id != self.id:
                    raise DoubleSpend('input `{}` was already spent'
                                      .format(input_txid))

                input_conditions.append(input_tx.conditions[input_cid])
                input_txs.append(input_tx)
                if input_tx.conditions[input_cid].amount < 1:
                    raise AmountError('`amount` needs to be greater than zero')
                input_amount += input_tx.conditions[input_cid].amount

            # validate asset id
            asset_id = Asset.get_asset_id(input_txs)
            if asset_id != self.asset.data_id:
                raise AssetIdMismatch(('The asset id of the input does not'
                                       ' match the asset id of the'
                                       ' transaction'))

            # get the asset creation to see if its divisible or not
            asset = bigchain.get_asset_by_id(asset_id)
            # validate the asset
            asset.validate_asset(amount=input_amount)
            # validate the amounts
            output_amount = 0
            for condition in self.conditions:
                if condition.amount < 1:
                    raise AmountError('`amount` needs to be greater than zero')
                output_amount += condition.amount

            if output_amount != input_amount:
                raise AmountError(('The amount used in the inputs `{}`'
                                   ' needs to be same as the amount used'
                                   ' in the outputs `{}`')
                                  .format(input_amount, output_amount))

        else:
            allowed_operations = ', '.join(Transaction.ALLOWED_OPERATIONS)
            raise TypeError('`operation`: `{}` must be either {}.'
                            .format(self.operation, allowed_operations))

        if not self.fulfillments_valid(input_conditions):
            raise InvalidSignature()
        else:
            return self

    @classmethod
    def from_dict(cls, tx_body):
        validate_transaction_schema(tx_body)
        return super().from_dict(tx_body)


class Block(object):
    """Bundle a list of Transactions in a Block. Nodes vote on its validity.

    Attributes:
        transaction (:obj:`list` of :class:`~.Transaction`):
            Transactions to be included in the Block.
        node_pubkey (str): The public key of the node creating the
            Block.
        timestamp (str): The Unix time a Block was created.
        voters (:obj:`list` of :obj:`str`): A list of a federation
            nodes' public keys supposed to vote on the Block.
        signature (str): A cryptographic signature ensuring the
            integrity and validity of the creator of a Block.
    """

    def __init__(self, transactions=None, node_pubkey=None, timestamp=None,
                 voters=None, signature=None):
        """The Block model is mainly used for (de)serialization and integrity
        checking.

        Args:
            transaction (:obj:`list` of :class:`~.Transaction`):
                Transactions to be included in the Block.
            node_pubkey (str): The public key of the node creating the
                Block.
            timestamp (str): The Unix time a Block was created.
            voters (:obj:`list` of :obj:`str`): A list of a federation
                nodes' public keys supposed to vote on the Block.
            signature (str): A cryptographic signature ensuring the
                integrity and validity of the creator of a Block.
        """
        if transactions is not None and not isinstance(transactions, list):
            raise TypeError('`transactions` must be a list instance or None')
        else:
            self.transactions = transactions or []

        if voters is not None and not isinstance(voters, list):
            raise TypeError('`voters` must be a list instance or None')
        else:
            self.voters = voters or []

        if timestamp is not None:
            self.timestamp = timestamp
        else:
            self.timestamp = gen_timestamp()

        self.node_pubkey = node_pubkey
        self.signature = signature

    def __eq__(self, other):
        try:
            other = other.to_dict()
        except AttributeError:
            return False
        return self.to_dict() == other

    def validate(self, bigchain):
        """Validate the Block.

        Args:
            bigchain (:class:`~bigchaindb.Bigchain`): An instantiated Bigchain
                object.

        Returns:
            :class:`~.Block`: If valid, return a `Block` object. Else an
            appropriate exception describing the reason of invalidity is
            raised.

        Raises:
            OperationError: If a non-federation node signed the Block.
            InvalidSignature: If a Block's signature is invalid.
        """

        # First, make sure this node hasn't already voted on this block
        if bigchain.has_previous_vote(self.id, self.voters):
            return self

        # Check if the block was created by a federation node
        possible_voters = (bigchain.nodes_except_me + [bigchain.me])
        if self.node_pubkey not in possible_voters:
            raise OperationError('Only federation nodes can create blocks')

        if not self.is_signature_valid():
            raise InvalidSignature('Block signature invalid')

        # Finally: Tentative assumption that every blockchain will want to
        # validate all transactions in each block
        for tx in self.transactions:
            # NOTE: If a transaction is not valid, `is_valid` will throw an
            #       an exception and block validation will be canceled.
            bigchain.validate_transaction(tx)

        return self

    def sign(self, private_key):
        """Create a signature for the Block and overwrite `self.signature`.

        Args:
            private_key (str): A private key corresponding to
                `self.node_pubkey`.

        Returns:
            :class:`~.Block`
        """
        block_body = self.to_dict()
        block_serialized = serialize(block_body['block'])
        private_key = PrivateKey(private_key)
        self.signature = private_key.sign(block_serialized.encode()).decode()
        return self

    def is_signature_valid(self):
        """Check the validity of a Block's signature.

        Returns:
            bool: Stating the validity of the Block's signature.
        """
        block = self.to_dict()['block']
        # cc only accepts bytestring messages
        block_serialized = serialize(block).encode()
        public_key = PublicKey(block['node_pubkey'])
        try:
            # NOTE: CC throws a `ValueError` on some wrong signatures
            #       https://github.com/bigchaindb/cryptoconditions/issues/27
            return public_key.verify(block_serialized, self.signature)
        except (ValueError, AttributeError):
            return False

    @classmethod
    def from_dict(cls, block_body):
        """Transform a Python dictionary to a Block object.

        Args:
            block_body (dict): A block dictionary to be transformed.

        Returns:
            :class:`~Block`

        Raises:
            InvalidHash: If the block's id is not corresponding to its
                data.
            InvalidSignature: If the block's signature is not corresponding
                to it's data or `node_pubkey`.
        """
        # TODO: Reuse `is_signature_valid` method here.
        block = block_body['block']
        block_serialized = serialize(block)
        block_id = hash_data(block_serialized)
        public_key = PublicKey(block['node_pubkey'])

        try:
            signature = block_body['signature']
        except KeyError:
            signature = None

        if block_id != block_body['id']:
            raise InvalidHash()

        if signature is not None:
            # NOTE: CC throws a `ValueError` on some wrong signatures
            #       https://github.com/bigchaindb/cryptoconditions/issues/27
            try:
                signature_valid = public_key\
                        .verify(block_serialized.encode(), signature)
            except ValueError:
                signature_valid = False
            if signature_valid is False:
                raise InvalidSignature('Invalid block signature')

        transactions = [Transaction.from_dict(tx) for tx
                        in block['transactions']]

        return cls(transactions, block['node_pubkey'],
                   block['timestamp'], block['voters'], signature)

    @property
    def id(self):
        return self.to_dict()['id']

    def to_dict(self):
        """Transform the Block to a Python dictionary.

        Returns:
            dict: The Block as a dict.

        Raises:
            OperationError: If the Block doesn't contain any transactions.
        """
        if len(self.transactions) == 0:
            raise OperationError('Empty block creation is not allowed')

        block = {
            'timestamp': self.timestamp,
            'transactions': [tx.to_dict() for tx in self.transactions],
            'node_pubkey': self.node_pubkey,
            'voters': self.voters,
        }
        block_serialized = serialize(block)
        block_id = hash_data(block_serialized)

        return {
            'id': block_id,
            'block': block,
            'signature': self.signature,
        }

    def to_str(self):
        return serialize(self.to_dict())
