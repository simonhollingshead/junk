import csv
import sys
from dataclasses import dataclass
from enum import Enum
from datetime import date, datetime


class SecurityType(Enum):
    BILL = 'Bill'
    CONVENTIONAL = 'Conventional'
    INDEXLINKED = 'Index-Linked'
    STRIP = 'STRIPS'  # acronym, so all-caps


SecurityToType = {'Bills': SecurityType.BILL,
                  'Conventional': SecurityType.CONVENTIONAL,
                  'Index-linked': SecurityType.INDEXLINKED,
                  'Strips': SecurityType.STRIP}


@dataclass(eq=True, frozen=True)
class Security:
    ISIN: str
    Type: SecurityType
    Coupon: float
    Maturity: date
    Dirty: float
    GrossAER: float


if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <path> <tax_rate>")
    print()
    print("path: Path to a .csv export from https://reports.tradeweb.com/closing-prices/gilts/ (no on-site filtering required).")
    print("tax_rate: Your income tax rate percentage (e.g. 0, 20, 40, 45, ...)")
    sys.exit(1)

tax_rate = float(sys.argv[2])
if (tax_rate <= 1 and tax_rate != 0) or tax_rate > 100:
    # <=1 probably means someone entered 0.4 for 40%.
    # However, indicating 0% tax is acceptable.
    print(
        f"Parameter two should be your prevailing tax rate.  You set {tax_rate}% which seemed illogical.")
    sys.exit(1)

assets = []
with open(sys.argv[1], 'r') as f:
    print("IMPORTANT: This script is not tax advice nor financial advice.  It probably contains errors.")
    print("Do your own evaluation of how taxation works for your specific circumstances before buying any securities.")
    print("Do not rely on this script to be kept up to date as taxation laws change.")
    print()

    # For some very weird reason, while I export the file and get DD/MM/YYYY, I've had a report that someone else gets MM/DD/YYYY.
    # I need to scan through the maturity dates to identify which of the two this file is in.
    # Since bill expiry dates seem to be every 7 days, I should pretty quickly run across an unambiguous date (X/Y/Z where X or Y > 13).
    # Yes, this is a hack, but it's *effective*.
    print("Identifying whether file is DD/MM/YYYY or MM/DD/YYYY... ", end='')
    csv_reader = csv.reader(f)
    next(csv_reader)  # Remove the headers.
    date_format = None
    for row in csv_reader:
        try:
            datetime.strptime(row[5], r"%d/%m/%Y")
        except ValueError:
            print("Found MM/DD/YYYY.")
            date_format = r"%m/%d/%Y"
        if not date_format:
            try:
                datetime.strptime(row[5], r"%m/%d/%Y")
            except ValueError:
                print("Found DD/MM/YYYY.")
                date_format = r"%d/%m/%Y"
        if date_format:
            break
    if not date_format:
        # At least one of the dates should have been unambiguous (e.g. the bill that matures on 2073-03-22).
        print("Somehow it wasn't possible to tell what the date format was.  This should never happen!  Are you sure you've done a full export?")
        sys.exit(1)

    # Rewind back to the start now we know what the date format is.
    f.seek(0)
    next(csv_reader)  # Remove the headers.
    for row in csv_reader:
        # Parse out all relevant data from the record.
        gilt_name = row[0]
        export_date = datetime.strptime(row[1], date_format).date()
        type = SecurityToType[row[3]]
        coupon = float(row[4]) if row[4] != "N/A" else 0
        maturity_date = datetime.strptime(row[5], date_format).date()
        days_to_maturity = (maturity_date - export_date).days
        clean = float(row[6]) if row[6] != "N/A" else 100
        dirty = float(row[7]) if row[7] != "N/A" else clean

        if maturity_date <= date.today():
            # It doesn't make sense to calculate for securities that have matured between the export date and today.
            continue

        if not gilt_name.lower().startswith("uk"):
            # This is a EuroGov bond.  Out of scope for this program.
            continue

        total_gross_return = 0
        # The amount of total_gross_return which is taxable.
        taxable_return = 0

        match type:
            case SecurityType.STRIP:
                # Strips are Deeply Discounted Securities with special calculation methods.
                # https://www.gov.uk/hmrc-internal-manuals/savings-and-investment-manual/saim3130
                # DELIBERATELY NOT IMPLEMENTED HERE.
                continue
            case SecurityType.INDEXLINKED:
                # Modelling the return of something index-linked is somewhat impossible if you don't know what inflation will be into the future.
                # DELIBERATELY NOT IMPLEMENTED HERE.
                continue
            case SecurityType.BILL:
                # No coupon, return entirely based on increase in price by the maturity date.
                # Officially these are deeply discounted securities and you must pay income tax on the gains.
                # https://community.hmrc.gov.uk/customerforums/cgt/97bf6f33-1231-ee11-a81c-0022481b8935
                total_gross_return = 100 - dirty
                taxable_return = total_gross_return
            case SecurityType.CONVENTIONAL:
                # Income tax is charged on the coupons, but they are capital gains free.
                # By using the dirty price we already take note of any interest accrued but unpaid (which isn't taxable as interest).
                taxable_return = coupon * (days_to_maturity/365)
                total_gross_return = (100 - dirty) + taxable_return

        total_net_return = total_gross_return - \
            (taxable_return * (tax_rate / 100))
        percentage_return = total_net_return/dirty
        annual_equiv = pow((percentage_return + 1), 365/days_to_maturity)-1

        assets.append(Security(ISIN=row[2],
                      Type=type,
                      Coupon=coupon,
                      Maturity=maturity_date,
                      Dirty=dirty,
                      GrossAER=annual_equiv))

assets.sort(key=lambda x: x.GrossAER, reverse=True)
print()
print(f"| {'':12} | {'':12} | {'':7} | {'':10} | {'':^7} | {'Comparison AER':^17} |")
print(f"| {'ISIN':^12} | {'Type':^12} | {'Coupon':>7} | {'Maturity':^10} | {'Price':^7} | {'Net':^7} | {'Gross':^7} |")
for asset in assets:
    print(f'| {asset.ISIN:12} | {asset.Type.value:^12} | {asset.Coupon:6.3f}% | {asset.Maturity} | {asset.Dirty:7.3f} | {asset.GrossAER:7.3%} | {asset.GrossAER/(1-(tax_rate/100)) if asset.GrossAER >= 0 else asset.GrossAER:7.3%} |')
