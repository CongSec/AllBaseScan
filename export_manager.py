# -*- coding: utf-8 -*-
import os
import csv
from PyQt5.QtCore import QThread
from constants import DATA_DIR

class ExportThread(QThread):
    def __init__(self, results, filename):
        super().__init__()
        self.results = results
        self.filename = filename

    def run(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(self.filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['keywords', 'keywords_raw', 'remark', 'line_number', 'nearby_lines', 'nearby_chars',
                            'down_lines', 'up_lines', 'source', 'file_path', 'exclude_text', 'use_regex']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for result in self.results:
                    writer.writerow(result)
        except Exception as e:
            raise e