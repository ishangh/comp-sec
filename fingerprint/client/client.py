import json
import logging
import pathlib

from datetime import datetime
from phe import paillier, EncryptedNumber, PaillierPublicKey, PaillierPrivateKey

import client.util as util
import client.dbhandler as dbhandler
from server.server import Server

from client.exceptions import AuthFailed, DuplicateUser

class Client:
    """
    Implements functionality to enroll and verify fingerprints
    and store them in a cloud database.
    """

    def __init__(self):
        """
        Initialize a client object.
        Create a logger object used to log data.
        Create a server object for communication with the server.
        """
        self.logger = self.get_logger()
        self.server = Server()

    def enroll(self, user):
        """
        Performs enrollment of a user.
        Provided a unique roll number, a pin and a fingerprint.
        It enrolls a user into the system and stores it's fingerprint in the database.

        :param user: dictionary containing required user information
        """
        user_roll_no = user['roll_no']
        user_pin = user['pin']
        user_fingerprint = user['fingerprint']

        data = dbhandler.read_data('userdata.json')
        for entry in data:
            if user_roll_no == entry['roll_no']:
                raise DuplicateUser
                return

        user_pub_key, user_priv_key = paillier.generate_paillier_keypair()
        user_vcode = util.generate_verification_code()
        user_shuffle_code = util.generate_shuffle_code()

        transformed_fingerprint = util.enrollment_transform(
            user_fingerprint, user_vcode, user_shuffle_code)
        encrypted_fingerprint = util.paillier_encrypt_vector(
            user_pub_key, transformed_fingerprint)

        user_tid = self.server.store_template(
            encrypted_fingerprint, user_pub_key.n)

        util.store_credentials(user_roll_no, user_pin, user_tid,
                          user_pub_key, user_priv_key, user_vcode, user_shuffle_code)

    def verify(self, user):
        """
        Verifies a user, given roll number, pin and a fingerprint

        :param user: dictionary containing required user information
        """
        user_roll_no = user['roll_no']
        user_pin = user['pin']
        user_fingerprint = user['fingerprint']

        user_data = util.retrieve_credentials(user_roll_no, user_pin)
        if not user_data:
            return
        user_tid = user_data['tid']
        user_vcode = user_data['vcode']
        user_shuffle_code = user_data['scode']
        user_pub_key = PaillierPublicKey(user_data['n'])
        user_priv_key = PaillierPrivateKey(
            user_pub_key, user_data['p'], user_data['q'])
        transformed_fingerprint = util.verification_transform(
            user_fingerprint, user_vcode, user_shuffle_code)

        # Server side
        euclidean_distance_cipher = self.server.compute_euclidean(
            transformed_fingerprint, user_tid)

        # Client side
        euclidean_distance = user_priv_key.decrypt(
            EncryptedNumber(user_pub_key, euclidean_distance_cipher))
        print(f'Eucledian distance computed: {euclidean_distance}')
        # Server side
        if self.server.make_decision(euclidean_distance):
            data = dbhandler.read_data('authhistory.json')
            data.append(
                {
                    'roll_no': user_roll_no,
                    'timestamp': datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                }
            )
            dbhandler.write_data(data, 'authhistory.json')
            # Stores timestamp of authentication
            # server.mark_authentication(user_roll_no)
        else:
            raise AuthFailed

    def get_auth_history_by_roll_no(self, roll_no):
        data = dbhandler.read_data('authhistory.json')
        history = []
        for entry in data:
            if entry['roll_no'] == roll_no:
                history.append(entry)
        return history

    def get_auth_history(self):
        roll_no = input('Enter roll no to search: ')
        history = self.get_auth_history_by_roll_no(roll_no)
        if not history:
            print(f'No entry found')
        else:
            for h in history:
                print(h['timestamp'])

    def get_logger(self):
        """
        Create a logging object for server logs

        :return: logger object
        """
        logger = logging.getLogger('client')
        logger.setLevel(level=logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s: %(module)s: [%(levelname)s]: %(message)s')

        file_name = pathlib.Path(__file__).parent / 'logs/client.log'
        file_handler = logging.FileHandler(file_name)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger
