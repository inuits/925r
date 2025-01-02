from calendar import monthrange
import datetime
from itertools import product
import logging
import random

from dateutil.relativedelta import relativedelta
from dateutil import tz
from django.conf import settings
from django.contrib.auth.models import User, Group
from django_countries import countries

from ninetofiver.models import (
    Timesheet,
    WorkSchedule,
    Leave,
    LeaveType,
    LeaveDate,
    Company,
    ContractGroup,
    ContractRole,
    ContractUser,
    ProjectContract,
    SupportContract,
    PerformanceType,
    ActivityPerformance,
    Location,
    ConsultancyContract,
    ApiKey,
    ContractLogType,
    ContractEstimate,
    EmploymentContractType,
    EmploymentContract,
    Holiday,
    Whereabout,
    TrainingType,
    Invoice,
    UserTraining,
    Training,
    InvoiceItem,
    Contract,
    STATUS_PENDING,
    STATUS_APPROVED,
)

log = logging.getLogger(__name__)


def get_random_date(start_date, end_date):
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days

    random_number_of_days = random.randrange(days_between_dates)
    random_date = start_date + datetime.timedelta(days=random_number_of_days)

    return random_date


def get_random_datetime(start_datetime, end_datetime):
    time_between_dates = end_datetime - start_datetime
    minutes_between_dates = time_between_dates.seconds // 60

    random_number_of_minutes = random.randrange(minutes_between_dates)
    random_datetime = start_datetime + datetime.timedelta(
        minutes=random_number_of_minutes
    )

    return random_datetime


def xprint(*args, **kwargs):
    print(" ".join(map(str, args)), **kwargs)


class TestDBPupulator:
    def __init__(self, default_size, perf_tables_size):
        if not settings.DEBUG:
            log.error("settings.DEBUG is False. Aborting")
            exit(1)

        self.default_range = range(1, default_size + 1)
        self.perf_tables_range = range(1, perf_tables_size + 1)
        self.activity_performances = []
        self.api_keys = []
        self.companies = []
        self.companies_customers = []
        self.contract_groups = []
        self.contract_log_types = []
        self.contract_roles = []
        self.contract_users = []
        self.contracts = []
        self.employment_contract = []
        self.employment_contract_type = []
        self.holidays = []
        self.invoices = []
        self.leavedates = []
        self.leaves = []
        self.leavetypes = []
        self.locations = []
        self.perf_types = []
        self.timesheets = []
        self.training_types = []
        self.user_trainings = []
        self.trainings = []
        self.users = []
        self.whereabouts = []
        self.work_schedules = []
        self.invoice_items = []
        self.contract_estimates = []

    def execute(self):
        """Order of methods is important"""
        self._populate_basic_tables()
        self._populate_performance_tables()
        self._populate_leave_tables()
        self._populate_additional_tables()

    def _populate_basic_tables(self):
        """
        This fills basic tables with data for debugging purposes
        when modifying, make sure to change all lists related to the object
        """
        xprint("Populate basic tables")

        self.leavetypes = [
            ("Vacation", "vacation", False, False),
            ("Sickness", "sickness", False, True),
            ("Recup", "recup", True, False),
            ("Unpaid", "unpaid", False, False),
        ]
        for leave_name, leave_desc, leave_overtime, leave_sickness in self.leavetypes:
            lt = LeaveType(
                name=leave_name,
                description=leave_desc,
                overtime=leave_overtime,
                sickness=leave_sickness,
            )
            lt.save()
        xprint(" - LeaveType:", len(self.leavetypes))

        companies_example = [
            ("Inuits CZ", "CZ12345678", "Zamenhofova 440 108 00 Prague 5", "CZ", True),
            ("CorpCZ1", "CZ12345679", "Lublaňská 689/40 120 00 Prague 2", "CZ", False),
            ("CorpCZ2", "CZ12345680", "Krakášova 88/1 120 00 Brno", "CZ", False),
            ("Inuits BE", "BE12345678", "Platteberg 8 9000 Ghent", "BE", True),
            ("CorpBE1", "BE12345679", "Ocean drive 42 2060 Antwerpen", "BE", False),
            ("CorpBE2", "BE12345680", "Rue Lens 11 1000 Bruxelles", "BE", False),
            ("Inuits PL", "PL12345678", "Daszyńskiego 15 33-332 Kraków", "PL", True),
            ("CorpPL1", "PL12345679", "Kinowa 18 04-017 Warszawa", "PL", False),
            ("CorpPL2", "PL12345680", "Chorzowska 5 40-121 Katowice", "PL", False),
        ]
        for (
            company_name,
            company_vat,
            company_addr,
            company_country,
            company_internal,
        ) in companies_example:
            com = Company(
                name=company_name,
                vat_identification_number=company_vat,
                address=company_addr,
                country=company_country,
                internal=company_internal,
            )
            com.save()
            self.companies.append(com)
        xprint(" - Company:", len(self.companies))

        locations_examples = [
            "Home",
            "Brasschaat",
            "Ghent",
            "Hasselt",
            "Prague",
            "Brno",
            "Kraków",
            "Kiev",
        ]
        for loc_name in locations_examples:
            loc = Location(name=loc_name)
            loc.save()
            self.locations.append(loc)
        xprint(" - Location:", len(self.locations))

        perf_types_example = [
            ("Minimal", "minimal", 0.50),
            ("Normal", "normal", 1.00),
            ("Overtime", "overtime", 1.50),
            ("Overtime", "overtime", 2.00),
        ]
        for pt_name, pt_description, pt_multiplier in perf_types_example:
            pt = PerformanceType(
                name=pt_name, description=pt_description, multiplier=pt_multiplier
            )
            pt.save()
            self.perf_types.append(pt)
        xprint(" - PerformanceType:", len(self.perf_types))

        work_schedules_example = [
            ("Fulltime1 (8h/day)", 8.00, 8.00, 8.00, 8.00, 8.00, 0.00, 0.00),
            ("Fulltime2 (7.6h/day)", 7.60, 7.60, 7.60, 7.60, 7.60, 0.00, 0.00),
            ("Parttime1 (6h/day)", 6.00, 6.00, 6.00, 6.00, 6.00, 0.00, 0.00),
            ("Parttime2 (6.4h/day)", 6.40, 6.40, 6.40, 6.40, 6.40, 0.00, 0.00),
            ("Zero", 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
        ]
        for (
            ws_name,
            ws_mon,
            ws_tue,
            ws_wed,
            ws_thu,
            ws_fri,
            ws_sat,
            ws_sun,
        ) in work_schedules_example:
            ws = WorkSchedule(
                name=ws_name,
                monday=ws_mon,
                tuesday=ws_tue,
                wednesday=ws_wed,
                thursday=ws_thu,
                friday=ws_fri,
                saturday=ws_sat,
                sunday=ws_sun,
            )
            ws.save()
            self.work_schedules.append(ws)
        xprint(" - WorkSchedule:", len(self.work_schedules))

    def _populate_performance_tables(self):
        """
        Fills higher amount of test data to all contract/performance-related tables
        Populate db with users, companies, customers, contract_groups
        """
        xprint("Populate performance tables")

        for i in self.default_range:
            cr = ContractRole(
                name="Contract role " + str(i),
                description="Description for contract role",
            )
            self.contract_roles.append(cr)
        # For more information about when and how to use bulk_create method follow the link:
        # https://docs.djangoproject.com/en/4.0/ref/models/querysets/#bulk-create
        ContractRole.objects.bulk_create(self.contract_roles)
        xprint(" - ContractRole:", len(self.contract_roles))

        # Its ok to have smaller no. of records for these tables
        for i in self.default_range:
            usr = User(
                username="test_user_" + str(i),
                email="test_" + str(i) + "@mail.com",
                first_name="User" + str(i),
                last_name="Inuit",
                is_active=random.choice([True, True, True, False]),
            )
            usr.save()
            self.users.append(usr)
            country = random.choice(["CZ", "BE", "PL"])
            comp = Company(
                vat_identification_number=(country + "00" + str(i)),
                name="test_company_" + str(i),
                address="address_test_company_" + str(i),
                country=country,
                internal=True,
            )
            comp.full_clean()
            comp.save()
            self.companies.append(comp)

            comp_cust = Company(
                vat_identification_number=(country + "000" + str(i)),
                name="test_company_customer_" + str(i),
                address="address_test_company_customer_" + str(i),
                country=country,
                internal=False,
            )
            comp_cust.full_clean()
            comp_cust.save()
            self.companies_customers.append(comp_cust)

            cg = ContractGroup(name="test_contract_group_" + str(i))
            cg.save()
            self.contract_groups.append(cg)

        xprint(" - User:", len(self.users))
        xprint(" - Company:", len(self.companies))
        xprint(" - ContractGroup:", len(self.contract_groups))

        # create staff_group
        staff_group = Group(name="staff")
        staff_group.save()
        
        # add userinfo
        for user in self.users:
            user.userinfo.country = random.choice(["CZ", "BE", "PL"])
            user.userinfo.gender = random.choice(["m", "f"])
            user.userinfo.save(update_fields=["country", "gender"])

        # Create staff users
        staff_users = [
            ("PavelTom", "pavel.tom@email.cz", "Pavel", "Tom", 1, 1, "CZ", "m"),
            ("MartinaHrb", "martina.hrb@email.cz", "Martina", "Hrb", 1, 1, "CZ", "f"),
            ("JohanaVan", "johana.van@email.be", "Johana", "Van", 1, 1, "BE", "f"),
            ("JeroenTux", "jeroen.tux@email.be", "Jeroen", "Tux", 1, 1, "BE", "m"),
            ("JakubMuz", "jakub.muz@email.pl", "Jakub", "Muz", 1, 0, "PL", "m"),
        ]
        for (
            username,
            email,
            first_name,
            last_name,
            is_staff,
            is_active,
            country,
            gender,
        ) in staff_users:
            user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_staff=is_staff,
                is_active=is_active,
            )
            user.save()
            user.groups.add(staff_group)
            self.users.append(user)
            user.userinfo.country = country
            user.userinfo.gender = gender
            user.userinfo.save()

        # add birth_date to users in user_info table
        for user in self.users:
            user.userinfo.birth_date = get_random_date(
                datetime.date(1970, 1, 1), datetime.date(2005, 1, 1)
            )
            user.userinfo.save(update_fields=["birth_date"])

        # populate contracts & activity performances -> higher number of records is good
        for x in self.perf_tables_range:
            start = get_random_date(
                datetime.date(2017, 1, 1), datetime.date(2021, 1, 1)
            )
            end = get_random_date(datetime.date(2021, 9, 9), datetime.date(2030, 1, 1))
            proj_cont = ProjectContract(
                name="test_project_contract_" + str(x),
                description="Test project contract " + str(x),
                customer=self.companies_customers[
                    random.randrange(len(self.companies_customers))
                ],
                company=self.companies[random.randrange(len(self.companies))],
                starts_at=start,
                ends_at=end,
                active=1,
                fixed_fee=round(random.uniform(200, 1000), 2),
            )
            start = get_random_date(
                datetime.date(2017, 1, 1), datetime.date(2021, 1, 1)
            )
            end = get_random_date(datetime.date(2021, 9, 9), datetime.date(2030, 1, 1))
            cons_cont = ConsultancyContract(
                name="test_consultancy_contract_" + str(x),
                description="Test consultancy contract " + str(x),
                customer=self.companies_customers[
                    random.randrange(len(self.companies_customers))
                ],
                company=self.companies[random.randrange(len(self.companies))],
                starts_at=start,
                ends_at=end,
                active=1,
                duration=round(random.uniform(10, 100), 1),
                day_rate=round(random.uniform(10, 100), 2),
            )
            start = get_random_date(
                datetime.date(2017, 1, 1), datetime.date(2021, 1, 1)
            )
            end = get_random_date(datetime.date(2021, 9, 9), datetime.date(2030, 1, 1))
            supp_cont = SupportContract(
                name="test_support_contract_" + str(x),
                description="Test support contract " + str(x),
                customer=self.companies_customers[
                    random.randrange(len(self.companies_customers))
                ],
                company=self.companies[random.randrange(len(self.companies))],
                starts_at=start,
                ends_at=end,
                active=1,
                day_rate=round(random.uniform(10, 100), 2),
                fixed_fee=round(random.uniform(200, 1000), 2),
                complexity=random.choice([1, 2, 4, 10, 20, 50, 100, 200]),
            )

            proj_cont.save()
            cons_cont.save()
            supp_cont.save()
            self.contracts.append(proj_cont)
            self.contracts.append(cons_cont)
            self.contracts.append(supp_cont)
        xprint(" - Contract:", len(self.contracts))

        # add contract users - all have Cotract role 1
        self.contract_roles = ContractRole.objects.all()
        for item in product(self.users, self.contracts):
            cu = ContractUser(
                user=item[0],
                contract=item[1],
                contract_role=self.contract_roles[0],
            )
            self.contract_users.append(cu)
        ContractUser.objects.bulk_create(self.contract_users)
        xprint(" - ContractUser:", len(self.contract_users))

        self.create_timesheets()

        # add performance
        # 10 for every timesheet, random contracts
        for ts in self.timesheets:
            for x in range(1, 11):
                days_in_month = monthrange(ts.year, ts.month)[1]

                act_perf = ActivityPerformance(
                    timesheet=ts,
                    date=datetime.date(
                        ts.year, ts.month, random.randint(1, days_in_month)
                    ),
                    contract=self.contracts[random.randrange(len(self.contracts))],
                    performance_type=self.perf_types[1],
                    contract_role=self.contract_roles[0],
                    description="test_activity_performance_" + str(x),
                    duration=random.randrange(1, 9),
                )
                act_perf.save()
                self.activity_performances.append(act_perf)
        xprint(" - ActivityPerformance:", len(self.activity_performances))

        # change Contracts with end_at before today as inactive
        # has to be done after creating Performances - it can not be created on inactive Contract
        contracts = Contract.objects.all()
        for contract in contracts:
            if contract.ends_at < datetime.date.today():
                contract.active = 0
                contract.save(update_fields=["active"])

    def create_timesheets(self):
        """Create a new timesheet for the current month for each user."""
        today = datetime.date.today()
        next_month = datetime.date.today() + relativedelta(months=1)

        for user in self.users:
            if user.is_active:
                # Ensure timesheet for this month exists
                ts_this_month, _ = Timesheet.objects.get_or_create(
                    user=user, month=today.month, year=today.year
                )

                # Ensure timesheet for next month exists
                ts_next_month, _ = Timesheet.objects.get_or_create(
                    user=user, month=next_month.month, year=next_month.year
                )

                self.timesheets.append(ts_this_month)
                self.timesheets.append(ts_next_month)
        xprint(" - Timesheet:", len(self.timesheets))

    def _populate_leave_tables(self):
        # Add holidays
        xprint("Populate holiday tables")
        holiday_dates = []
        for x in range(1000):
            holiday_date = get_random_date(
                datetime.date(2017, 1, 1), datetime.date(2030, 1, 1)
            )
            holiday_dates.append(holiday_date)
            ho = Holiday(
                name="Holiday " + str(x),
                date=holiday_date,
                country=random.choice(["CZ", "BE", "PL"]),
            )
            ho.save()
            self.holidays.append(ho)
        xprint(" - Holidays:", len(self.holidays))

        # Add leaves
        xprint("Populate leave tables")
        for usr in self.users:
            if usr.is_active:
                # load all timesheets for user
                timesheets_for_user = Timesheet.objects.filter(user=usr)
                # invalid days are holidays
                invalid_dates = list(holiday_dates)

                # Vacation half day
                lv1 = Leave(
                    user=usr,
                    leave_type=LeaveType.objects.get(name="Vacation"),
                    description="#test - vacation half day",
                )
                lv1.save()
                self.leaves.append(lv1)
                # select randomly one timesheet for user
                ts = timesheets_for_user[random.randrange(len(timesheets_for_user))]
                searching_for_date = True
                while searching_for_date:
                    date_vacation = get_random_date(
                        datetime.datetime(
                            ts.year, ts.month, 1, tzinfo=tz.gettz("Europe/Prague")
                        ),
                        datetime.datetime(
                            ts.year, ts.month, 1, tzinfo=tz.gettz("Europe/Prague")
                        )
                        + relativedelta(months=1)
                        - datetime.timedelta(days=1),
                    )
                    weekday = date_vacation.weekday()
                    saturday = 5
                    if weekday < saturday and (date_vacation.date() not in invalid_dates):
                        invalid_dates.append(date_vacation.date())
                        ld1 = LeaveDate(
                            leave=lv1,
                            timesheet=ts,
                            starts_at=date_vacation.replace(
                                hour=9, minute=00, second=1
                            ),
                            ends_at=date_vacation.replace(
                                hour=13, minute=00, second=00
                            ),
                        )
                        ld1.save()
                        self.leavedates.append(ld1)
                        break
                lv1.status = (
                    STATUS_APPROVED
                    if ld1.starts_at
                    < datetime.datetime.now(tz=tz.gettz("Europe/Prague"))
                    else STATUS_PENDING
                )
                lv1.save(update_fields=["status"])

                # Vacation 3 days
                lv2 = Leave(
                    user=usr,
                    leave_type=LeaveType.objects.get(name="Vacation"),
                    description="#test - vacation 3 days",
                )
                lv2.save()
                self.leaves.append(lv2)
                # select randomly one timesheet for user
                ts = timesheets_for_user[random.randrange(len(timesheets_for_user))]
                searching_for_date = True
                while searching_for_date:
                    dates_vacation = []
                    date1_vacation = get_random_date(
                        datetime.datetime(
                            ts.year, ts.month, 1, tzinfo=tz.gettz("Europe/Prague")
                        ),
                        datetime.datetime(
                            ts.year, ts.month, 1, tzinfo=tz.gettz("Europe/Prague")
                        )
                        + relativedelta(months=1)
                        - datetime.timedelta(days=3),
                    )
                    dates_vacation.append(date1_vacation)
                    date2_vacation = date1_vacation + relativedelta(days=1)
                    dates_vacation.append(date2_vacation)
                    date3_vacation = date1_vacation + relativedelta(days=2)
                    dates_vacation.append(date3_vacation)
                    weekday = date1_vacation.weekday()
                    thursday = 3
                    if (
                        weekday < thursday
                        and (date1_vacation.date() not in invalid_dates)
                        and (date2_vacation.date() not in invalid_dates)
                        and (date3_vacation.date() not in invalid_dates)
                    ):
                        for date in dates_vacation:
                            invalid_dates.append(date.date())
                            ld2 = LeaveDate(
                                leave=lv2,
                                timesheet=ts,
                                starts_at=date.replace(hour=9, minute=00, second=1),
                                ends_at=date.replace(hour=17, minute=00, second=00),
                            )
                            ld2.save()
                            self.leavedates.append(ld2)
                        break
                lv2.status = (
                    STATUS_APPROVED
                    if ld2.starts_at
                    < datetime.datetime.now(tz=tz.gettz("Europe/Prague"))
                    else STATUS_PENDING
                )
                lv2.save(update_fields=["status"])

                # Sickness
                lv3 = Leave(
                    user=usr,
                    leave_type=LeaveType.objects.get(name="Sickness"),
                    description="#test - sickness",
                )
                lv3.save()
                self.leaves.append(lv3)
                # select randomly one timesheet for user
                ts = timesheets_for_user[random.randrange(len(timesheets_for_user))]
                while searching_for_date:
                    date_sickness = get_random_date(
                        datetime.datetime(
                            ts.year, ts.month, 1, tzinfo=tz.gettz("Europe/Prague")
                        ),
                        datetime.datetime(
                            ts.year, ts.month, 1, tzinfo=tz.gettz("Europe/Prague")
                        )
                        + relativedelta(months=1)
                        - datetime.timedelta(days=1),
                    )
                    weekday = date_sickness.weekday()
                    saturday = 5
                    if weekday < saturday and (date_sickness.date() not in invalid_dates):
                        invalid_dates.append(date_sickness.date())
                        ld3 = LeaveDate(
                            leave=lv3,
                            timesheet=ts,
                            starts_at=date_sickness.replace(
                                hour=9, minute=00, second=1
                            ),
                            ends_at=date_sickness.replace(
                                hour=17, minute=00, second=00
                            ),
                        )
                        ld3.save()
                        self.leavedates.append(ld3)
                        break
                lv3.status = (
                    STATUS_APPROVED
                    if ld3.starts_at
                    < datetime.datetime.now(tz=tz.gettz("Europe/Prague"))
                    else STATUS_PENDING
                )
                lv3.save(update_fields=["status"])

        xprint(" - Leave:", len(self.leaves))
        xprint(" - LeaveDate:", len(self.leavedates))

    def _populate_additional_tables(self):
        xprint("Populate additional tables")

        for i, user in enumerate(self.users):
            ak = ApiKey(
                name="API test key " + str(i),
                user=user,
            )
            ak.save()
            self.api_keys.append(ak)
        xprint(" - ApiKey:", len(self.api_keys))

        # in one loop ContractLogType, EmploymentContractType, Whereabout
        for i in self.default_range:
            clt = ContractLogType(
                name="Contract log type " + str(i),
            )
            clt.save()
            self.contract_log_types.append(clt)

            ect = EmploymentContractType(
                name="Employment contract type " + str(i),
            )
            ect.save()
            self.employment_contract_type.append(ect)

            tsheet = self.timesheets[i % len(self.timesheets)]
            random_day = random.randint(1, 28)

            wa = Whereabout(
                timesheet=tsheet,
                location=self.locations[i % len(self.locations)],
                starts_at=get_random_datetime(
                    datetime.datetime(
                        tsheet.year,
                        tsheet.month,
                        random_day,
                        0,
                        0,
                        tzinfo=tz.gettz("Europe/Prague"),
                    ),
                    datetime.datetime(
                        tsheet.year,
                        tsheet.month,
                        random_day,
                        11,
                        59,
                        tzinfo=tz.gettz("Europe/Prague"),
                    ),
                ),
                ends_at=get_random_datetime(
                    datetime.datetime(
                        tsheet.year,
                        tsheet.month,
                        random_day,
                        12,
                        0,
                        tzinfo=tz.gettz("Europe/Prague"),
                    ),
                    datetime.datetime(
                        tsheet.year,
                        tsheet.month,
                        random_day,
                        23,
                        59,
                        tzinfo=tz.gettz("Europe/Prague"),
                    ),
                ),
            )
            wa.save()
            self.whereabouts.append(wa)

        xprint(" - ContractLogType:", len(self.contract_log_types))
        xprint(" - EmploymentContractType:", len(self.employment_contract_type))
        xprint(" - Whereabout:", len(self.whereabouts))

        # Create Employment contracts - user has to have at least one active contract with internal company

        companies_internal = Company.objects.filter(internal=True)
        for i, user in enumerate(self.users):
            company_index = i % len(companies_internal)
            company = companies_internal[company_index]
            prev_company = companies_internal[
                company_index - 1 if company_index > 0 else len(companies_internal) - 1
            ]  # grab another company so we can create an expired contract

            if user.is_staff:
                company = (
                    Company.objects.get(name="Inuits CZ")
                    if user.userinfo.country == "CZ"
                    else Company.objects.get(name="Inuits BE")
                    if user.userinfo.country == "BE"
                    else Company.objects.get(name="Inuits PL")
                    if user.userinfo.country == "PL"
                    else company
                )
            ec = EmploymentContract(
                user=user,
                company=company,
                employment_contract_type=self.employment_contract_type[
                    i % len(self.employment_contract_type)
                ],
                work_schedule=self.work_schedules[0],  # it is 8h/day for all users
                started_at=get_random_date(
                    datetime.date(2021, 1, 2), datetime.date(2022, 1, 1)
                ),
                ended_at=get_random_date(
                    datetime.date(2024, 2, 2), datetime.date(2030, 1, 1)
                ),
            )
            ec.save()

            # create expirated employment contract
            ec_exp = EmploymentContract(
                user=user,
                company=prev_company,
                employment_contract_type=self.employment_contract_type[
                    i % len(self.employment_contract_type)
                ],
                work_schedule=self.work_schedules[0],
                started_at=get_random_date(
                    datetime.date(2012, 1, 1), datetime.date(2018, 1, 1)
                ),
                ended_at=get_random_date(
                    datetime.date(2018, 2, 2), datetime.date(2021, 1, 1)
                ),
            )
            ec_exp.save()
            self.employment_contract.append(ec)
            self.employment_contract.append(ec_exp)
        xprint(" - EmploymentContract:", len(self.employment_contract))

        for contract in self.contracts:
            inv = Invoice(
                contract=contract,
                period_starts_at=get_random_date(
                    datetime.date(2017, 1, 1), datetime.date(2021, 1, 1)
                ),
                period_ends_at=get_random_date(
                    datetime.date(2021, 2, 2), datetime.date(2030, 1, 1)
                ),
                date=get_random_date(
                    datetime.date(2021, 2, 2), datetime.date(2030, 1, 1)
                ),
                reference=f"Reference {contract.id}",
                description=f"Customer {contract.customer.id}",
            )
            inv.save()
            self.invoices.append(inv)

            con_est = ContractEstimate(
                contract=contract,
                contract_role=self.contract_roles[0],
                duration=random.randrange(1, 100),
            )
            con_est.save()
            self.contract_estimates.append(con_est)

        xprint(" - Invoice:", len(self.invoices))
        xprint(" - ContractEstimate:", len(self.contract_estimates))

        for item in self.invoices:
            inv_item = InvoiceItem(
                invoice=item,
                price=random.randrange(10, 100),
                amount=random.randrange(1, 3),
                description=f"Description {item.id}",
            )
            inv_item.save()
            self.invoice_items.append(inv_item)
        xprint(" - InvoiceItem:", len(self.invoice_items))

        for i in range(1, 11):
            tt = TrainingType(
                name="Training type " + str(i),
                country=(list(countries)[random.randrange(len(countries))])[
                    0
                ],  # random country code from countries
                description="Description of training type",
            )
            tt.save()
            self.training_types.append(tt)
        xprint(" - TrainingType:", len(self.training_types))

        for user in self.users:
            ut = UserTraining(user=user)
            ut.save()
            self.user_trainings.append(ut)
        xprint(" - UserTraining:", len(self.user_trainings))

        for i in range(1, 20):
            training = Training(
                user_training=random.choice(self.user_trainings),
                training_type=random.choice(self.training_types),
            )
            training.save()
            self.trainings.append(training)
        xprint(" - Training:", len(self.trainings))

        xprint("Populator complete!")
