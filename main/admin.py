from django.contrib import admin
from .models import Profile, Mentor, Student, Semester, Placement

# -------------------------
# Profile Admin
# -------------------------
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_type', 'phone')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone')
    list_filter = ('user_type',)


# -------------------------
# Mentor Admin
# -------------------------
@admin.register(Mentor)
class MentorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'department', 'phone')
    search_fields = ('name', 'email', 'department', 'phone')


# -------------------------
# Inline Placement for Student
# -------------------------
class PlacementInline(admin.TabularInline):
    model = Placement
    extra = 1
    fields = ('company', 'position', 'package', 'status', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True
    ordering = ('-created_at',)  # show newest first


# -------------------------
# Inline Semester for Student
# -------------------------
class SemesterInline(admin.TabularInline):
    model = Semester
    extra = 1
    fields = ('semester_number', 'gpa')
    show_change_link = True
    ordering = ('semester_number',)  # ascending order


# -------------------------
# Student Admin
# -------------------------
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'branch', 'mentor', 'cgpa', 'display_semesters', 'display_top_offer')
    search_fields = ('name', 'email', 'branch', 'mentor__name')
    list_filter = ('branch', 'mentor')
    inlines = [PlacementInline, SemesterInline]

    def display_semesters(self, obj):
        """Display semester GPAs from related Semester objects"""
        semesters = obj.semesters.all().order_by('semester_number')
        if semesters.exists():
            return ", ".join([f"Sem {s.semester_number}: {s.gpa}" for s in semesters])
        return "-"
    display_semesters.short_description = 'Semester GPAs'

    def display_top_offer(self, obj):
        """Show top accepted placement"""
        top = obj.top_offer  # Assuming Student model has a top_offer property
        if top:
            return f"{top.company} ({top.package})"
        return "-"
    display_top_offer.short_description = 'Top Offer'


# -------------------------
# Placement Admin
# -------------------------
@admin.register(Placement)
class PlacementAdmin(admin.ModelAdmin):
    list_display = ('student', 'company', 'position', 'package', 'package_unit', 'status', 'created_at')
    search_fields = ('student__name', 'company', 'position')
    list_filter = ('status', 'company')
    ordering = ('-created_at',)

# -------------------------
# Semester Admin
# -------------------------
@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('student', 'semester_number', 'gpa')
    search_fields = ('student__name',)
    list_filter = ('semester_number',)
    ordering = ('semester_number',)
