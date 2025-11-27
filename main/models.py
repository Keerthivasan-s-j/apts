from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg



class Profile(models.Model):
    USER_TYPES = [
        ('student', 'Student'),
        ('mentor', 'Mentor'),
        ('tpo', 'TPO'),
        ('principal', 'Principal'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    user_type = models.CharField(max_length=20, choices=USER_TYPES)
    phone = models.CharField(max_length=15, blank=True, null=True)

    def full_name(self):
        return self.user.first_name + " " + self.user.last_name

    def __str__(self):
        return f"{self.user.username} ({self.user_type})"


class Mentor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mentor_profile')
    name = models.CharField(max_length=100)
    email = models.EmailField()
    department = models.CharField(max_length=100, default="Computer Science")
    phone = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.name


# class Student(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
#     name = models.CharField(max_length=100)
#     email = models.EmailField()
#     branch = models.CharField(max_length=50)
#     mentor = models.ForeignKey(Mentor, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
#     cgpa = models.FloatField(default=0.0)
#     attendance = models.PositiveIntegerField(default=0)
#     credits = models.PositiveIntegerField(default=0)

#     @property
#     def package_lpa(self):
#         return float(self.package) / 100000  # convert INR to LPA

#     @property
#     def top_offer(self):
#         # Get only accepted offers
#         offers = self.placements.filter(status="Accepted")
#         if not offers.exists():
#             return None
#         # max based on numeric package
#         return max(offers, key=lambda o: float(o.package))


#     @property
#     def full_name(self):
#         return f"{self.user.first_name} {self.user.last_name}"

#     def __str__(self):
#         return self.name

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    name = models.CharField(max_length=100)
    email = models.EmailField()
    branch = models.CharField(max_length=50)
    mentor = models.ForeignKey(Mentor, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    
    cgpa = models.FloatField(default=0.0)
    attendance = models.PositiveIntegerField(default=0)
    credits = models.PositiveIntegerField(default=0)

    # NEW FIELD
    current_semester = models.PositiveIntegerField(default=1)

    @property
    def package_lpa(self):
        return float(self.package) / 100000  # convert INR to LPA

    @property
    def top_offer(self):
        # Get only accepted offers
        offers = self.placements.filter(status="Accepted")
        if not offers.exists():
            return None
        # max based on numeric package
        return max(offers, key=lambda o: float(o.package))


    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}"

    def __str__(self):
        return self.name


@receiver(post_save, sender=Student)
def create_semesters(sender, instance, created, **kwargs):
    if created:
        for sem_num in range(1, 9):
            Semester.objects.get_or_create(student=instance, semester_number=sem_num, defaults={'gpa': 0.0})

class Semester(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='semesters')
    semester_number = models.PositiveIntegerField()
    gpa = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('student', 'semester_number')
        ordering = ['semester_number']

    def __str__(self):
        return f"{self.student.name} - Sem {self.semester_number}: {self.gpa}"

class Placement(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
    ]

    UNIT_CHOICES = [
        ('LPA', 'LPA'),
        ('K', 'K'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='placements')
    company = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    package = models.FloatField(default=0.0, help_text="Enter numeric value only")
    package_unit = models.CharField(max_length=3, choices=UNIT_CHOICES, default='LPA')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def package_in_lpa(self):
        """Return package in LPA for comparison."""
        if self.package_unit == 'LPA':
            return self.package
        elif self.package_unit == 'K':
            return self.package / 100  # convert thousands to LPA
        return self.package

    # @property
    # def top_offer(self):
    #     """Return the Placement with the highest numeric package in LPA for this student."""
    #     offers = self.student.placements.all()
    #     top = None
    #     top_value = 0
    #     for offer in offers:
    #         pkg_value = offer.package_in_lpa
    #         if pkg_value > top_value:
    #             top_value = pkg_value
    #             top = offer
    #     return top

    def __str__(self):
        return f"{self.student.name} - {self.company} ({self.status})"
