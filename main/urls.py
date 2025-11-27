from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path("signup/", views.signup_view, name="signup"),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Home
    path('', views.home, name='home'),

    # Student Dashboard
    path('student/<int:student_id>/', views.std_dashboard, name='std_dashboard'),

    # Mentor Dashboard
    path('mentor/dashboard/', views.mentor_dashboard, name='mentor_dashboard'),
    path('mentor/export/csv/', views.mentor_export_csv, name='mentor_export_csv'),

    # Placement CRUD
    path('student/<int:student_id>/placement/add/', views.add_placement, name='add_placement'),
    path('placement/<int:placement_id>/edit/', views.edit_placement, name='edit_placement'),
    path('placement/<int:placement_id>/delete/', views.delete_placement, name='delete_placement'),

    # Update CGPA & Semester GPAs (AJAX endpoint)
    path('student/<int:student_id>/update_cgpa/', views.update_cgpa, name='update_cgpa'),
    path('student/<int:student_id>/semester/<int:sem_num>/update/', views.update_semester_gpa, name='update_semester_gpa'),

    path('tpo/dashboard/', views.tpo_dashboard, name='tpo_dashboard'),
    path('tpo/assign/', views.assign_mentor, name='assign_mentor'),

    path("tpo/bulk_assign/", views.bulk_assign_mentor, name="bulk_assign_mentor"),
    path("tpo/export/csv/", views.export_students_csv, name="export_students_csv"),
    path("tpo/placements/", views.tpo_placements, name="tpo_placements"),

    path("tpo/placements/export/csv/", views.export_placements_csv, name="export_placements_csv"),
    path("tpo/ai/", views.tpo_ai_query, name="tpo_ai_query"),
    path("student/ai/<int:student_id>/", views.student_ai_query, name="student_ai_query"),


]
