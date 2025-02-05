from datetime import datetime, timedelta
from pathlib import Path
import json

from src.database import Bill, Plan, CheckIn


def secure_str(s: str) -> str:
    half = len(s) // 2
    return s[:half] + "*" * (len(s) - half)


def monthly_bill(year: int, month: int):
    print(f"Checking {year}-{month} bills...")

    bills = Bill.select().where(
        Bill.created_at.year == year,
        Bill.created_at.month == month,
    )

    print("\n==== Orders ====\n")

    all_plans = Plan.select().order_by(Plan.valid_days)
    daily_amount = [0] * 32
    plans = {}
    for plan in all_plans:
        plans[plan.plan_id] = (plan.title, 0, 0, 0)  # name, order, item, amount

    order_count = 0
    item_count = 0
    bill_amount = 0
    order_csv = "order_id,plan,buy_count,amount,remark,user_id,created_at,expired_at\n"
    remark_csv = order_csv
    for bill in bills:
        remark = (
            json.loads(bill.raw_data)
            .get("data", {})
            .get("list", [{}])[0]
            .get("remark", "")
        )
        csv_line = f"{secure_str(bill.order_id)},{plans[bill.plan_id][0]},{bill.buy_count},{bill.actually_paid},{remark},{secure_str(bill.user_id)},{bill.created_at},{bill.expired_at}\n"
        order_csv += csv_line
        if remark:
            remark_csv += csv_line

        day = bill.created_at.day
        daily_amount[day] += float(bill.actually_paid)

        if bill.plan_id not in plans:
            print(f"Plan not found: {bill.plan_id}, bill: {bill}")
            continue

        plans[bill.plan_id] = (
            plans[bill.plan_id][0],
            plans[bill.plan_id][1] + 1,
            plans[bill.plan_id][2] + bill.buy_count,
            plans[bill.plan_id][3] + float(bill.actually_paid),
        )

        order_count += 1
        item_count += bill.buy_count
        bill_amount += float(bill.actually_paid)

    print("Daily amount:")
    for day, amount in enumerate(daily_amount):
        if day == 0 or amount == 0:
            continue
        print(f"{year}-{month}-{day}: {amount:.2f}")

    print("\nPlans:")
    for plan_id, (name, order, item, amount) in plans.items():
        print(f"{name}: {order} orders, {item} items, amount: {amount:.2f}")

    print(
        f"\nTotal: orders: {order_count}, items: {item_count}, amount: {bill_amount:.2f}"
    )

    Path(f"csv/{year}-{month}").mkdir(parents=True, exist_ok=True)
    with open(
        f"csv/{year}-{month}/{year}-{month} orders.csv", "w", encoding="utf-8"
    ) as f:
        f.write("\ufeff")  # BOM
        f.write(order_csv)

    with open(
        f"csv/{year}-{month}/{year}-{month} remarks.csv", "w", encoding="utf-8"
    ) as f:
        f.write("\ufeff")  # BOM
        f.write(remark_csv)

    print("\n==== Checkins ====\n")

    checkins = CheckIn.select().where(
        CheckIn.activated_at.year == year,
        CheckIn.activated_at.month == month,
    )

    # 有可能订单是以前的，但是激活是在这个月的
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    # 但也别太久远了，最多三个月前
    if month <= 3:
        prev_month = datetime(year - 1, 12 + month - 3, 1)
    else:
        prev_month = datetime(year, month - 3, 1)

    plan_titles = {plan.plan_id: plan.title for plan in all_plans}

    bills = Bill.select().where(
        Bill.created_at < next_month,
        Bill.created_at >= prev_month,
    )

    app_uas = {}
    csvs = {}
    csv_head = "order_id,plan,buy_count,amount,remark,user_id,created_at,expired_at,activated_at\n"

    invalid_checkins = 0
    for checkin in checkins:
        app = checkin.application
        ua = checkin.user_agent
        app_ua = f"{app} - {ua}"
        if app_ua not in app_uas:
            app_uas[app_ua] = (0, 0)  # count, amount
            csvs[app_ua] = csv_head

        count = 0
        amount = 0
        for bill in bills:
            if bill.cdk == checkin.cdk:
                count += 1
                amount += float(bill.actually_paid)
                remark = (
                    json.loads(bill.raw_data)
                    .get("data", {})
                    .get("list", [{}])[0]
                    .get("remark", "")
                )
                csvs[
                    app_ua
                ] += f"{secure_str(bill.order_id)},{plan_titles[bill.plan_id]},{bill.buy_count},{bill.actually_paid},{remark},{secure_str(bill.user_id)},{bill.created_at},{bill.expired_at},{checkin.activated_at}\n"

        if count == 0:
            invalid_checkins += 1
            continue

        app_uas[app_ua] = (
            app_uas[app_ua][0] + 1,
            app_uas[app_ua][1] + amount,
        )

    checkin_count = len(checkins) - invalid_checkins
    checkin_amount = sum(amount for _, (_, amount) in app_uas.items())

    print(f"Invalid checkins: {invalid_checkins}")
    for app_ua, (count, amount) in app_uas.items():
        print(f"{app_ua}: {count} checkins, amount: {amount:.2f}")

    print(f"\nTotal: checkins: {checkin_count}, amount: {checkin_amount:.2f}")

    not_checkin_count = order_count - checkin_count
    not_checkin_amount = bill_amount - checkin_amount
    print(
        f"\nOrders not checkin: {not_checkin_count}, amount: {not_checkin_amount:.2f}\n"
    )

    Path(f"csv/{year}-{month}").mkdir(parents=True, exist_ok=True)
    for app_ua, csv in csvs.items():
        with open(
            f"csv/{year}-{month}/{year}-{month} {app_ua}.csv", "w", encoding="utf-8"
        ) as f:
            f.write("\ufeff")  # BOM
            f.write(csv)

    print(f"CSV saved to \"csv/{year}-{month}/\"")


if __name__ == "__main__":
    now = datetime.now()

    def pre_month(now):
        year = now.year
        month = now.month - 1
        if month == 0:
            year -= 1
            month = 12
        return year, month

    # monthly_bill(*pre_month(now))
    monthly_bill(now.year, now.month)
