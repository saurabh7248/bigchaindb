import time
import pytest


@pytest.mark.usefixtures('processes')
def test_double_create(b, user_vk):
    tx = b.create_transaction(b.me, user_vk, None, 'CREATE')
    tx = b.sign_transaction(tx, b.me_private)

    b.write_transaction(tx)
    time.sleep(2)
    b.write_transaction(tx)
    time.sleep(2)
    b.get_transaction(tx['id'])
