import gspread
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class GoogleSheetsCols(Enum):
    A=1
    B=2
    C=3
    D=4
    E=5
    F=6
    G=7
    H=8
    I=9
    J=10
    K=11
    L=12
    M=13
    N=14
    O=15

@dataclass
class ReportDataCells:
    floor_price_cell = (9, GoogleSheetsCols.F.value)
    total_buys_cell = (11, GoogleSheetsCols.B.value)
    percents_of_total_supply = (15, GoogleSheetsCols.B.value)
    avg_buy_price = (7, GoogleSheetsCols.B.value)
    unrealized_pnl = (10, GoogleSheetsCols.F.value)
    collection_name = (1, GoogleSheetsCols.F.value)
    stickerpack_name = (2, GoogleSheetsCols.F.value)

class SheetsClient:
    def __init__(self, credentials_path: str):
        self.credentials_path = credentials_path
        self.gc = None
        
    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API"""
        try:
            self.gc = gspread.service_account(filename=self.credentials_path)
            logger.info("Google Sheets authentication successful")
            return True
        except Exception as e:
            logger.error(f"Google Sheets authentication failed: {e}")
            return False
    
    def get_all_worksheets(self, sheet_key: str) -> List[gspread.Worksheet]:
        """Get all worksheets from a spreadsheet"""
        try:
            if not self.gc:
                raise Exception("Not authenticated")
            spreadsheet = self.gc.open_by_key(sheet_key)
            return spreadsheet.worksheets()
        except Exception as e:
            logger.error(f"Error getting worksheets: {e}")
            return []
    
    def get_collection_info(self, worksheet: gspread.Worksheet) -> Tuple[Optional[str], Optional[str]]:
        """Extract collection name and stickerpack name from worksheet"""
        try:
            collection_name = worksheet.cell(
                ReportDataCells.collection_name[0], 
                ReportDataCells.collection_name[1]
            ).value
            
            stickerpack_name = worksheet.cell(
                ReportDataCells.stickerpack_name[0], 
                ReportDataCells.stickerpack_name[1]
            ).value
            
            # Strip whitespace and handle empty values
            collection_name = collection_name.strip() if collection_name else None
            stickerpack_name = stickerpack_name.strip() if stickerpack_name else None
            
            return collection_name, stickerpack_name
            
        except Exception as e:
            logger.error(f"Error getting collection info from {worksheet.title}: {e}")
            return None, None
    
    def update_floor_price(self, worksheet: gspread.Worksheet, price: float) -> bool:
        """Update floor price in worksheet"""
        try:
            worksheet.update_cell(
                ReportDataCells.floor_price_cell[0], 
                ReportDataCells.floor_price_cell[1], 
                price
            )
            logger.info(f"Updated floor price to {price} in {worksheet.title}")
            return True
        except Exception as e:
            logger.error(f"Error updating floor price in {worksheet.title}: {e}")
            return False 