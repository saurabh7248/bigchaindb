import time
import pytest
import rethinkdb as r


@pytest.mark.usefixtures('processes')
def test_fast_double_create(b, user_vk):
    tx = b.create_transaction(b.me, user_vk, None, 'CREATE')
    tx = b.sign_transaction(tx, b.me_private)

    # write everything fast
    b.write_transaction(tx)
    b.write_transaction(tx)

    time.sleep(2)
    tx_returned = b.get_transaction(tx['id'])

    # test that the tx can be queried
    assert tx_returned == tx
    # test the transaction appears only once
    assert len(list(r.table('bigchain')
                    .get_all(tx['id'], index='transaction_id')
                    .run(b.conn))) == 1


@pytest.mark.usefixtures('processes')
def test_double_create(b, user_vk):
    tx = b.create_transaction(b.me, user_vk, None, 'CREATE')
    tx = b.sign_transaction(tx, b.me_private)

    b.write_transaction(tx)
    time.sleep(2)
    b.write_transaction(tx)
    time.sleep(2)
    tx_returned = b.get_transaction(tx['id'])

    # test that the tx can be queried
    assert tx_returned == tx
    # test the transaction appears only once
    assert len(list(r.table('bigchain')
                    .get_all(tx['id'], index='transaction_id')
                    .run(b.conn))) == 1
