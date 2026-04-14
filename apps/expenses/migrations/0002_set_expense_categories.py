from django.db import migrations


EXPENSE_CATEGORIES = [
    ("교우회 활동비", 10),
    ("교우회 모임지출", 20),
    ("결혼 축하기", 30),
    ("근조기", 40),
    ("학부 지원", 50),
]


def set_expense_categories(apps, schema_editor):
    expense_category = apps.get_model("expenses", "ExpenseCategory")
    active_names = []

    for name, sort_order in EXPENSE_CATEGORIES:
        active_names.append(name)
        expense_category.objects.update_or_create(
            name=name,
            defaults={"sort_order": sort_order, "is_active": True},
        )

    expense_category.objects.exclude(name__in=active_names).update(is_active=False)


def unset_expense_categories(apps, schema_editor):
    expense_category = apps.get_model("expenses", "ExpenseCategory")
    expense_category.objects.filter(name__in=[name for name, _ in EXPENSE_CATEGORIES]).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(set_expense_categories, unset_expense_categories),
    ]
