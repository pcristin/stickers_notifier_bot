import gspread
import logging
import time
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GoogleSheetsCols(Enum):
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8
    I = 9
    J = 10
    K = 11
    L = 12
    M = 13
    N = 14
    O = 15


@dataclass
class ReportDataCells:
    floor_price_cell = (9, GoogleSheetsCols.F.value)
    total_buys_cell = (11, GoogleSheetsCols.B.value)
    on_sale = (12, GoogleSheetsCols.B.value)
    total_sells = (13, GoogleSheetsCols.B.value)
    total_left = (14, GoogleSheetsCols.B.value)
    percents_of_total_supply = (15, GoogleSheetsCols.B.value)
    avg_buy_price = (7, GoogleSheetsCols.B.value)
    unrealized_pnl = (10, GoogleSheetsCols.F.value)
    collection_name = (1, GoogleSheetsCols.F.value)
    stickerpack_name = (2, GoogleSheetsCols.F.value)
    realized_pnl = (11, GoogleSheetsCols.F.value)
    collection_spent_on_markets = (6, GoogleSheetsCols.B.value)
    left_on_cold = (3, GoogleSheetsCols.B.value)


class SheetsClient:
    def __init__(
        self,
        credentials_path: str,
        read_delay: float = 0.0,
        worksheet_delay: float = 0.0,
    ):
        self.credentials_path = credentials_path
        self.gc = None
        self.read_delay = max(0.0, read_delay)
        self.worksheet_delay = max(0.0, worksheet_delay)

    def _sleep(self, delay: float) -> None:
        if delay > 0:
            time.sleep(delay)

    def _throttle_read(self) -> None:
        self._sleep(self.read_delay)

    def _throttle_between_worksheets(self) -> None:
        self._sleep(self.worksheet_delay)

    def _get_cell_value(
        self, worksheet: gspread.Worksheet, cell: Tuple[int, int]
    ) -> Optional[str]:
        value = worksheet.cell(cell[0], cell[1]).value
        self._throttle_read()
        return value

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

    def get_collection_info(
        self, worksheet: gspread.Worksheet
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract collection name and stickerpack name from worksheet"""
        try:
            collection_name = self._get_cell_value(
                worksheet, ReportDataCells.collection_name
            )

            stickerpack_name = self._get_cell_value(
                worksheet, ReportDataCells.stickerpack_name
            )

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
                price,
            )
            logger.info(f"Updated floor price to {price} in {worksheet.title}")
            return True
        except Exception as e:
            logger.error(f"Error updating floor price in {worksheet.title}: {e}")
            return False

    def get_worksheet_report_data(
        self, worksheet: gspread.Worksheet
    ) -> Optional[Dict[str, Any]]:
        """Extract all report data from a single worksheet"""
        try:
            # Get collection info
            collection_name, stickerpack_name = self.get_collection_info(worksheet)
            if not collection_name or not stickerpack_name:
                return None

            # Get all required values
            floor_price = self._get_cell_value(
                worksheet, ReportDataCells.floor_price_cell
            )

            total_buys = self._get_cell_value(
                worksheet, ReportDataCells.total_buys_cell
            )

            percent_supply = self._get_cell_value(
                worksheet, ReportDataCells.percents_of_total_supply
            )

            avg_buy_price = self._get_cell_value(
                worksheet, ReportDataCells.avg_buy_price
            )

            unrealized_pnl = self._get_cell_value(
                worksheet, ReportDataCells.unrealized_pnl
            )

            realized_pnl = self._get_cell_value(
                worksheet, ReportDataCells.realized_pnl
            )

            on_sale = self._get_cell_value(worksheet, ReportDataCells.on_sale)

            total_sells = self._get_cell_value(
                worksheet, ReportDataCells.total_sells
            )

            total_left = self._get_cell_value(
                worksheet, ReportDataCells.total_left
            )

            collection_spent_on_markets = self._get_cell_value(
                worksheet, ReportDataCells.collection_spent_on_markets
            )

            left_on_cold = self._get_cell_value(
                worksheet, ReportDataCells.left_on_cold
            )

            # Convert string values to appropriate types
            def safe_float(value):
                if value is None or value == "":
                    return 0.0
                try:
                    # Remove any percentage signs and convert
                    if isinstance(value, str):
                        value = value.replace("%", "").replace(",", ".")
                    return float(value)
                except (ValueError, TypeError):
                    return 0.0

            def safe_int(value):
                if value is None or value == "":
                    return 0
                try:
                    return int(float(str(value).replace(",", ".")))
                except (ValueError, TypeError):
                    return 0

            return {
                "worksheet_title": worksheet.title,
                "collection_name": collection_name,
                "stickerpack_name": stickerpack_name,
                "floor_price": safe_float(floor_price),
                "total_buys": safe_int(total_buys),
                "on_sale": safe_int(on_sale),
                "total_sells": safe_int(total_sells),
                "total_left": safe_int(total_left),
                "percent_supply": safe_float(percent_supply),
                "avg_buy_price": safe_float(avg_buy_price),
                "unrealized_pnl": safe_float(unrealized_pnl),
                "realized_pnl": safe_float(realized_pnl),
                "collection_spent_on_markets": safe_float(collection_spent_on_markets),
                "left_on_cold": safe_float(left_on_cold),
            }

        except Exception as e:
            logger.error(f"Error extracting report data from {worksheet.title}: {e}")
            return None

    def get_all_report_data(self, sheet_key: str) -> List[Dict[str, Any]]:
        """Get report data from all worksheets"""
        try:
            worksheets = self.get_all_worksheets(sheet_key)
            report_data = []

            for worksheet in worksheets:
                data = self.get_worksheet_report_data(worksheet)
                if data:
                    report_data.append(data)
                else:
                    logger.warning(
                        f"Skipped worksheet {worksheet.title} - missing or invalid data"
                    )
                self._throttle_between_worksheets()

            return report_data

        except Exception as e:
            logger.error(f"Error getting all report data: {e}")
            return []
