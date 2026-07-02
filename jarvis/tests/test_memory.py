import unittest
import os
import tempfile
from jarvis.memory.sqlite_store import SQLiteStore

class TestSQLiteStore(unittest.TestCase):
    def setUp(self):
        # Create a temporary file for the database
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.store = SQLiteStore(db_path=self.db_path)

    def tearDown(self):
        # Clean up the temporary database file and any WAL/shm files
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        wal_path = f"{self.db_path}-wal"
        shm_path = f"{self.db_path}-shm"
        if os.path.exists(wal_path):
            os.remove(wal_path)
        if os.path.exists(shm_path):
            os.remove(shm_path)

    def test_database_initialization(self):
        # Check that the database file was created
        self.assertTrue(os.path.exists(self.db_path))

    def test_add_and_retrieve_messages(self):
        # Add a few messages
        self.store.add_message("user", "Hello JARVIS")
        self.store.add_message("jarvis", "Hello User")
        self.store.add_message("user", "How are you?")

        # Retrieve messages
        messages = self.store.get_recent_messages(limit=5)
        
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Hello JARVIS")
        self.assertEqual(messages[1]["role"], "jarvis")
        self.assertEqual(messages[1]["content"], "Hello User")
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["content"], "How are you?")

    def test_limit_recent_messages(self):
        # Add 10 messages
        for i in range(10):
            self.store.add_message("user", f"Message {i}")

        # Retrieve with a limit of 3
        messages = self.store.get_recent_messages(limit=3)
        self.assertEqual(len(messages), 3)
        # They should be chronological (last 3 messages are 7, 8, 9)
        self.assertEqual(messages[0]["content"], "Message 7")
        self.assertEqual(messages[1]["content"], "Message 8")
        self.assertEqual(messages[2]["content"], "Message 9")

if __name__ == "__main__":
    unittest.main()
