import csv
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import (
    Avg, Count, Case, When, F, FloatField,
    Value, ExpressionWrapper, Q
)
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage

from google import genai

# Models
from .models import (
    Profile, Student, Mentor, Placement, Semester
)

# NEW Gemini client (correct way)
client = genai.Client(api_key="AIzaSyCH3yJnDI4UZY70yjC3FsOWPrWCr05SckQ")

@login_required
@csrf_exempt
def tpo_ai_query(request):
    if request.method != "POST":
        return JsonResponse({"reply": "Invalid request"}, status=400)

    data = json.loads(request.body)
    prompt = data.get("prompt", "")

    from main.models import Student, Placement, Mentor, Semester

    # Collect all relevant TPO data
    students = Student.objects.all()
    placements = Placement.objects.select_related("student")
    mentors = Mentor.objects.all()

    # Build academic summary
    academic_records = []
    for s in students:
        semesters = list(s.semesters.all().values("semester_number", "gpa"))
        academic_records.append({
            "name": s.name,
            "email": s.email,
            "branch": s.branch,
            "cgpa": s.cgpa,
            "current_semester": s.current_semester,
            "semesters": semesters,
            "mentor": s.mentor.name if s.mentor else "Not Assigned",
        })

    # Build placement summary
    placement_records = []
    for p in placements:
        placement_records.append({
            "student": p.student.name,
            "branch": p.student.branch,
            "company": p.company,
            "position": p.position,
            "package": p.package,
            "unit": p.package_unit,
            "status": p.status,
        })

    # Build mentor summary
    mentor_records = []
    for m in mentors:
        mentor_records.append({
            "name": m.name,
            "department": m.department,
            "students": list(Student.objects.filter(mentor=m).values("name", "branch"))
        })

    full_context = {
        "students": academic_records,
        "placements": placement_records,
        "mentors": mentor_records,
    }

    # AI Query (with HTML output)
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=f"""
        You are a Placement & Academic Analytics AI.

        Below is complete database context:
        {json.dumps(full_context)}

        User Question:
        {prompt}

        IMPORTANT:
        - Respond ONLY in clean HTML.
        - Do NOT use markdown.
        - Use <h3>, <p>, <ul>, <li>, <b> tags for formatting.
        - Make the explanation extremely clear and organized.
        """
    )

    reply_text = response.text if hasattr(response, "text") else "Error: No response"

    return JsonResponse({"reply": reply_text})

@login_required
@csrf_exempt
def student_ai_query(request, student_id):
    if request.method != "POST":
        return JsonResponse({"reply": "Invalid request"}, status=400)

    # Only the student himself can use this AI
    student = get_object_or_404(Student, id=student_id)
    if request.user != student.user:
        return JsonResponse({"reply": "Unauthorized."}, status=403)

    data = json.loads(request.body)
    prompt = data.get("prompt", "")

    # Build self-data only (strictly student-only)
    academic_data = {
        "name": student.name,
        "email": student.email,
        "branch": student.branch,
        "cgpa": student.cgpa,
        "current_semester": student.current_semester,
        "mentor": student.mentor.name if student.mentor else "No mentor assigned",
        "semesters": list(student.semesters.all().values("semester_number", "gpa")),
        "placements": list(student.placements.all().values(
            "company", "position", "package", "package_unit", "status"
        ))
    }

    # AI Client
    # client = genai.Client(api_key="YOUR_KEY")

    # AI Query
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=f"""
        You are a Student Guidance AI.
        The following is the student’s own academic + placement record:
        {json.dumps(academic_data)}

        User Question:
        {prompt}

        IMPORTANT RULES:
        - You are NOT allowed to show data of other students or mentors.
        - You may give guidance, tips, preparation strategy, and analysis.
        - Output MUST be in clean HTML.
        - Use <h3>, <p>, <ul>, <li>, <b> for clarity.
        - Keep tone friendly, encouraging, and clear.
        """
    )

    answer = response.text if hasattr(response, "text") else "No response."

    return JsonResponse({"reply": answer})


# -------------------------
# Signup View
# -------------------------
def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")
        user_type = request.POST.get("user_type")
        phone = request.POST.get("phone")

        # Prevent duplicate usernames or emails
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("signup")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect("signup")

        with transaction.atomic():
            # Create Django user
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
            )

            # Create Profile
            profile = Profile.objects.create(
                user=user,
                user_type=user_type,
                phone=phone
            )

            # Depending on type, create Student or Mentor
            if user_type == "student":
                branch = request.POST.get("branch")
                Student.objects.create(
                    user=user,
                    name=f"{first_name} {last_name}",
                    email=email,
                    branch=branch
                )

            elif user_type == "mentor":
                department = request.POST.get("department")
                Mentor.objects.create(
                    user=user,
                    name=f"{first_name} {last_name}",
                    email=email,
                    department=department
                )

        messages.success(request, "Account created successfully! Please login.")
        return redirect("login")

    return render(request, "signup.html")


# -------------------------
# Authentication Views
# -------------------------
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            if user.profile.user_type == "student":
                return redirect("std_dashboard", student_id=user.student_profile.id)

            elif user.profile.user_type == "mentor":
                return redirect("mentor_dashboard")

            elif user.profile.user_type == "tpo":
                return redirect("tpo_dashboard")

            else:
                return redirect("home")

        # if user is not None:
        #     login(request, user)
        #     return redirect("home")
        # else:
        #     messages.error(request, "Invalid username or password.")

    return render(request, "login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# -------------------------
# Home View
# -------------------------

def home(request):
    return render(request, "index.html")


# -------------------------
# Student Dashboard
# -------------------------
@login_required
def std_dashboard(request, student_id):
    student = get_object_or_404(Student, pk=student_id)

    # SECURITY CHECK
    if hasattr(request.user, "student_profile"):
        # student can only view himself
        if request.user.student_profile.id != student_id:
            return redirect("home")

    elif hasattr(request.user, "mentor_profile"):
        # mentor can view only their students
        if student.mentor != request.user.mentor_profile:
            return redirect("home")
    else:
        return redirect("home")  # block others (tpo, principal until you define)


    semesters = student.semesters.all()
    placements = student.placements.all().order_by('-created_at')

    accepted_count = placements.filter(status="Accepted").count()
    pending_count = placements.filter(status="Pending").count()
    rejected_count = placements.filter(status="Rejected").count()

    if accepted_count > 0:
        placement_status = "Placed"
    elif placements.exists():
        placement_status = "In Progress"
    else:
        placement_status = "Not Placed"

    context = {
        "student": student,
        "semesters": semesters,
        "placements": placements,
        "placement_status": placement_status,
        "accepted_count": accepted_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "current_sem": student.current_semester,
    }
    return render(request, "std_dashboard.html", context)


# -------------------------
# Mentor Dashboard
# -------------------------
# @login_required
# def mentor_dashboard(request):

#     if not hasattr(request.user, "mentor_profile"):
#         return redirect("home")

#     students = Student.objects.filter(mentor__user=request.user)

#     placed_count = sum(1 for s in students if s.placements.filter(status="Accepted").exists())
#     total_gpa = sum(s.cgpa for s in students)
#     avg_gpa = round(total_gpa / len(students), 2) if students else 0

#     # ADD THIS
#     for s in students:
#         s.has_accepted = s.placements.filter(status="Accepted").exists()
#         s.has_any = s.placements.exists()

#         s.display_status = (
#             "Placed" if s.has_accepted
#             else "In Progress" if s.has_any
#             else "Not Placed"
#         )

#         top = s.placements.filter(status="Accepted").order_by('-package').first()
#         s.top_company = top.company if top else "-"
#         s.top_role = top.position if top else "-"

#     context = {
#         "students": students,
#         "placed_count": placed_count,
#         "avg_gpa": avg_gpa,
#     }
#     return render(request, "mentor_dashboard.html", context)

@login_required
def mentor_dashboard(request):
    # ensure this user is a mentor
    if not hasattr(request.user, "mentor_profile"):
        return redirect("home")

    mentor = request.user.mentor_profile

    # Annotate placements with package in LPA for correct sorting/metrics
    package_in_lpa_expr = Case(
        When(package_unit='LPA', then=F('package')),
        When(package_unit='K', then=ExpressionWrapper(F('package') / Value(100.0), output_field=FloatField())),
        default=Value(0),
        output_field=FloatField()
    )

    # Base students queryset for this mentor
    students_qs = Student.objects.filter(mentor=mentor).select_related('user').prefetch_related('placements').annotate(
        avg_semester_gpa=Avg('semesters__gpa')  # optional aggregated field
    )

    # Filters & search params (from GET)
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")  # placed/in-progress/not-placed/all
    gpa_filter = request.GET.get("gpa", "all")  # high/medium/low/all
    sort = request.GET.get("sort", "name_asc")  # name_asc, cgpa_desc, cgpa_asc, package_desc, package_asc
    page = request.GET.get("page", 1)

    # Apply search
    if q:
        students_qs = students_qs.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
        )

    # Create helper fields for each student: has_any, has_accepted, top_package_lpa, top_offer info
    # We will build a list of dicts for template rendering (so we can compute top_offer easily)
    students = []
    for s in students_qs:
        placements = list(s.placements.all())
        # annotate package_lpa per placement:
        for p in placements:
            if p.package_unit == 'LPA':
                p.package_lpa = float(p.package or 0)
            elif p.package_unit == 'K':
                p.package_lpa = float(p.package or 0) / 100.0
            else:
                p.package_lpa = float(p.package or 0)

        has_any = len(placements) > 0
        has_accepted = any(p.status == "Accepted" for p in placements)
        top_offer = None
        if has_any:
            accepted_offers = [p for p in placements if p.status == "Accepted"]
            if accepted_offers:
                top_offer = max(accepted_offers, key=lambda o: o.package_lpa)
            else:
                # if no accepted, show highest package among any offers for preview
                top_offer = max(placements, key=lambda o: o.package_lpa)

        student_obj = {
            "obj": s,
            "name": s.full_name if hasattr(s, "full_name") else s.name,
            "email": s.email,
            "branch": s.branch,
            "cgpa": float(s.cgpa or 0),
            "attendance": s.attendance,
            "credits": s.credits,
            "has_any": has_any,
            "has_accepted": has_accepted,
            "top_offer": top_offer,   # may be None or Placement instance with package_lpa attribute
        }
        students.append(student_obj)

    # Apply status_filter and gpa_filter on the computed students list
    def status_match(st):
        if status_filter == "placed":
            return st["has_accepted"]
        elif status_filter == "in-progress":
            return (not st["has_accepted"]) and st["has_any"]
        elif status_filter == "not-placed":
            return (not st["has_any"])
        return True

    def gpa_match(st):
        g = st["cgpa"]
        if gpa_filter == "high":
            return g >= 8.5
        if gpa_filter == "medium":
            return 7.5 <= g < 8.5
        if gpa_filter == "low":
            return g < 7.5
        return True

    students = [s for s in students if status_match(s) and gpa_match(s)]

    # Sorting
    if sort == "cgpa_desc":
        students.sort(key=lambda s: s["cgpa"], reverse=True)
    elif sort == "cgpa_asc":
        students.sort(key=lambda s: s["cgpa"])
    elif sort == "package_desc":
        students.sort(key=lambda s: (s["top_offer"].package_lpa if s["top_offer"] else 0), reverse=True)
    elif sort == "package_asc":
        students.sort(key=lambda s: (s["top_offer"].package_lpa if s["top_offer"] else 0))
    else:  # default name_asc
        students.sort(key=lambda s: s["name"].lower())

    # Pagination (list -> paginate)
    per_page = 12
    paginator = Paginator(students, per_page)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Stats for mentor
    total_students = Student.objects.filter(mentor=mentor).count()
    placed_count = sum(1 for s in students if s["has_accepted"])
    avg_gpa = round(sum(s["cgpa"] for s in students) / len(students), 2) if students else 0
    highest_package = 0
    for s in students:
        if s["top_offer"]:
            highest_package = max(highest_package, s["top_offer"].package_lpa if s["top_offer"] else 0)

    # Top students for chart (by package)
    top_students = sorted([s for s in students if s["top_offer"]], key=lambda x: x["top_offer"].package_lpa, reverse=True)[:6]
    top_students_chart = [{"name": s["name"], "package": round(s["top_offer"].package_lpa, 2)} for s in top_students]

    # CGPA distribution buckets
    buckets = {"<7.5": 0, "7.5-8.4": 0, "8.5+": 0}
    for s in students:
        g = s["cgpa"]
        if g < 7.5:
            buckets["<7.5"] += 1
        elif g < 8.5:
            buckets["7.5-8.4"] += 1
        else:
            buckets["8.5+"] += 1

    # branches (for possible filter dropdown)
    branches = Student.objects.filter(mentor=mentor).values_list("branch", flat=True).distinct()

    context = {
        "mentor": mentor,
        "students_page": page_obj,   # paginated list of dicts
        "paginator": paginator,
        "total_students": total_students,
        "placed_count": placed_count,
        "avg_gpa": avg_gpa,
        "highest_package": round(highest_package, 2),
        "top_students_json": json.dumps(top_students_chart),
        "buckets_json": json.dumps(buckets),
        "branches": branches,
        "current_filters": {
            "q": q,
            "status": status_filter,
            "gpa": gpa_filter,
            "sort": sort
        },
        "query_string": request.GET.urlencode(),
    }

    return render(request, "mentor_dashboard.html", context)


@login_required
def mentor_export_csv(request):
    # ensure mentor
    if not hasattr(request.user, "mentor_profile"):
        return redirect("home")
    mentor = request.user.mentor_profile

    # Get the same students list as in mentor_dashboard (no pagination, but respecting filters)
    # Reuse logic: build base queryset, then compute student dicts
    base_qs = Student.objects.filter(mentor=mentor).select_related('user').prefetch_related('placements')
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    gpa_filter = request.GET.get("gpa", "all")
    sort = request.GET.get("sort", "name_asc")

    if q:
        base_qs = base_qs.filter(Q(name__icontains=q) | Q(email__icontains=q))

    students = []
    for s in base_qs:
        placements = list(s.placements.all())
        for p in placements:
            if p.package_unit == 'LPA':
                p.package_lpa = float(p.package or 0)
            elif p.package_unit == 'K':
                p.package_lpa = float(p.package or 0) / 100.0
            else:
                p.package_lpa = float(p.package or 0)
        has_any = len(placements) > 0
        has_accepted = any(p.status == "Accepted" for p in placements)
        top_offer = None
        if has_any:
            accepted_offers = [p for p in placements if p.status == "Accepted"]
            if accepted_offers:
                top_offer = max(accepted_offers, key=lambda o: o.package_lpa)
            else:
                top_offer = max(placements, key=lambda o: o.package_lpa)
        student_obj = {
            "name": s.full_name if hasattr(s, "full_name") else s.name,
            "email": s.email,
            "branch": s.branch,
            "cgpa": float(s.cgpa or 0),
            "has_any": has_any,
            "has_accepted": has_accepted,
            "top_offer": top_offer,
        }
        students.append(student_obj)

    # apply filters
    def status_match(st):
        if status_filter == "placed":
            return st["has_accepted"]
        elif status_filter == "in-progress":
            return (not st["has_accepted"]) and st["has_any"]
        elif status_filter == "not-placed":
            return (not st["has_any"])
        return True

    def gpa_match(st):
        g = st["cgpa"]
        if gpa_filter == "high":
            return g >= 8.5
        if gpa_filter == "medium":
            return 7.5 <= g < 8.5
        if gpa_filter == "low":
            return g < 7.5
        return True

    students = [s for s in students if status_match(s) and gpa_match(s)]

    # CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=mentor_students.csv'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Branch', 'CGPA', 'Placed', 'Top Company', 'Top Role', 'Top Package (LPA)'])

    for s in students:
        top = s['top_offer']
        writer.writerow([
            s['name'],
            s['email'],
            s['branch'],
            s['cgpa'],
            "Yes" if s['has_accepted'] else "No",
            top.company if top else "",
            top.position if top else "",
            round(top.package_lpa, 2) if top else ""
        ])

    return response



# -------------------------
# Placement CRUD Operations
# -------------------------
@login_required
def add_placement(request, student_id):
    student = get_object_or_404(Student, id=student_id)

    # SECURITY CHECK
    if request.user != student.user:
        return redirect("home")

    if request.method == "POST":
        company = request.POST.get("company")
        position = request.POST.get("position")
        package = request.POST.get("package")
        status = request.POST.get("status")

        Placement.objects.create(
            student=student,
            company=company,
            position=position,
            package=package,
            status=status,
        )
        messages.success(request, "Placement added successfully!")
        return redirect("std_dashboard", student_id=student_id)

    return redirect("std_dashboard", student_id=student_id)


@login_required
def edit_placement(request, placement_id):
    placement = get_object_or_404(Placement, id=placement_id)
    student = placement.student

    # SECURITY CHECK
    if request.user != student.user:
        return redirect("home")

    if request.method == "POST":
        placement.company = request.POST.get("company")
        placement.position = request.POST.get("position")
        placement.package = request.POST.get("package")
        placement.status = request.POST.get("status")
        placement.save()
        messages.success(request, "Placement updated successfully!")
        return redirect("std_dashboard", student_id=student.id)

    return redirect("std_dashboard", student_id=student.id)


@login_required
def delete_placement(request, placement_id):
    placement = get_object_or_404(Placement, id=placement_id)
    student = placement.student

    # SECURITY CHECK
    if request.user != student.user:
        return redirect("home")

    student_id = student.id
    placement.delete()
    messages.success(request, "Placement deleted successfully!")
    return redirect("std_dashboard", student_id=student_id)
    

# -------------------------
# Update Student GPA and Semesters
# -------------------------
# @login_required
# def update_cgpa(request, student_id):
#     student = get_object_or_404(Student, id=student_id)

#     # SECURITY CHECK
#     if request.user != student.user:
#         return redirect("home")

#     if request.method == "POST":
#         cgpa = request.POST.get("cgpa")
#         semesters_numbers = request.POST.getlist("semester_number[]")
#         gpas = request.POST.getlist("gpa[]")

#         student.cgpa = float(cgpa)
#         student.save()

#         for sem_num, gpa in zip(semesters_numbers, gpas):
#             semester_obj, created = Semester.objects.get_or_create(
#                 student=student,
#                 semester_number=int(sem_num),
#                 defaults={'gpa': float(gpa)}
#             )
#             if not created:
#                 semester_obj.gpa = float(gpa)
#                 semester_obj.save()

#         return redirect("std_dashboard", student_id=student_id)

#     return redirect("std_dashboard", student_id=student_id)

@login_required
def update_cgpa(request, student_id):
    student = get_object_or_404(Student, id=student_id)

    if request.user != student.user and not hasattr(request.user, "mentor_profile") and request.user.profile.user_type != "tpo":
        return redirect("home")

    if request.method == "POST":
        cgpa = request.POST.get("cgpa")
        current_sem = int(request.POST.get("current_sem"))
        semesters_numbers = request.POST.getlist("semester_number[]")
        gpas = request.POST.getlist("gpa[]")

        student.current_semester = current_sem

        # Save semesters
        for sem_num, gpa in zip(semesters_numbers, gpas):
            semester_obj, created = Semester.objects.get_or_create(
                student=student,
                semester_number=int(sem_num),
                defaults={'gpa': float(gpa)}
            )
            semester_obj.gpa = float(gpa)
            semester_obj.save()

        # Instead of using all semesters, compute CGPA only till current_semester - 1
        cutoff = student.current_semester - 1
        valid_semesters = Semester.objects.filter(student=student, semester_number__lte=cutoff)

        if valid_semesters.exists():
            student.cgpa = sum(s.gpa for s in valid_semesters) / valid_semesters.count()
        else:
            student.cgpa = 0.0

        student.save()


        return redirect("std_dashboard", student_id=student_id)

    return redirect("std_dashboard", student_id=student_id)



# @login_required
# def tpo_dashboard(request):

#     # Allow only TPO
#     if request.user.profile.user_type != "tpo":
#         return redirect("home")

#     students = Student.objects.all().select_related('mentor', 'user')
#     mentors = Mentor.objects.all().select_related('user')

#     context = {
#         "students": students,
#         "mentors": mentors,
#     }
#     return render(request, "tpo_dashboard.html", context)

@login_required
def update_semester_gpa(request, student_id, sem_num):
    """
    Update a single semester GPA for a student, recalc student's cgpa as average of semesters.
    Expects POST: 'gpa' numeric value.
    """
    student = get_object_or_404(Student, id=student_id)

    # Permission check: only the student himself OR the student's mentor OR a TPO can update
    user_allowed = False
    if hasattr(request.user, "student_profile") and request.user.student_profile.id == student.id:
        user_allowed = True
    elif hasattr(request.user, "mentor_profile") and student.mentor == request.user.mentor_profile:
        user_allowed = True
    elif hasattr(request.user, "profile") and request.user.profile.user_type == "tpo":
        user_allowed = True

    if not user_allowed:
        messages.error(request, "Not authorized to edit this semester.")
        return redirect("std_dashboard", student_id=student_id)

    if request.method == "POST":
        gpa_raw = request.POST.get("gpa")
        try:
            gpa_val = float(gpa_raw)
        except (TypeError, ValueError):
            messages.error(request, "Invalid GPA value.")
            return redirect("std_dashboard", student_id=student_id)

        semester_obj = Semester.objects.filter(student=student, semester_number=sem_num).first()
        if not semester_obj:
            # create if missing
            semester_obj = Semester.objects.create(student=student, semester_number=sem_num, gpa=gpa_val)
        else:
            semester_obj.gpa = gpa_val
            semester_obj.save()

        # Recompute student's CGPA as average of existing semester GPAs (non-zero semesters only)
        sems = student.semesters.all()
        if sems.exists():
            total = sum((s.gpa or 0.0) for s in sems)
            count = sems.count()
            new_cgpa = round(total / count, 2)
        else:
            new_cgpa = 0.0

        student.cgpa = new_cgpa
        student.save()

        messages.success(request, f"Semester {sem_num} updated. CGPA is now {new_cgpa}.")
        return redirect("std_dashboard", student_id=student_id)

    return redirect("std_dashboard", student_id=student_id)

@login_required
def tpo_dashboard(request):

    if request.user.profile.user_type != "tpo":
        return redirect("home")

    students = Student.objects.all().select_related("mentor", "user")
    mentors = Mentor.objects.all()

    # Filters
    branch = request.GET.get("branch")
    mentor_id = request.GET.get("mentor")
    placement_status = request.GET.get("status")

    if branch and branch != "all":
        students = students.filter(branch=branch)

    if mentor_id and mentor_id != "all":
        students = students.filter(mentor_id=mentor_id)

    if placement_status:
        if placement_status == "placed":
            students = [s for s in students if s.placements.filter(status="Accepted").exists()]
        elif placement_status == "in-progress":
            students = [s for s in students if s.placements.exists() and not s.placements.filter(status="Accepted").exists()]
        elif placement_status == "not-placed":
            students = [s for s in students if not s.placements.exists()]

    placements = Placement.objects.all()
    total_students = Student.objects.count()
    placed = placements.filter(status="Accepted").values("student").distinct().count()
    not_placed = total_students - placed
    in_progress = placements.filter(status="Pending").count()

    avg_cgpa = round(Student.objects.all().aggregate(avg=Avg("cgpa"))["avg"] or 0, 2)
    highest_package = max([p.package_in_lpa for p in placements], default=0)

    context = {
        "students": students,
        "mentors": mentors,
        "branches": Student.objects.values_list("branch", flat=True).distinct(),
        "context_stats": {
            "total_students": total_students,
            "placed": placed,
            "not_placed": not_placed,
            "in_progress": in_progress,
            "avg_cgpa": avg_cgpa,
            "highest_package": highest_package,
        }
    }

    return render(request, "tpo_dashboard.html", context)


@login_required
def assign_mentor(request):
    
    # Only TPO can do this
    if request.user.profile.user_type != "tpo":
        return redirect("home")

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        mentor_id = request.POST.get("mentor_id")

        student = get_object_or_404(Student, id=student_id)

        if mentor_id == "none":
            student.mentor = None
        else:
            mentor = get_object_or_404(Mentor, id=mentor_id)
            student.mentor = mentor

        student.save()
        messages.success(request, "Mentor updated successfully!")
        return redirect("tpo_dashboard")

    return redirect("tpo_dashboard")

@login_required
def bulk_assign_mentor(request):

    if request.user.profile.user_type != "tpo":
        return redirect("home")

    if request.method == "POST":
        mentor_id = request.POST.get("mentor_id")
        students_selected = request.POST.getlist("students[]")

        mentor = Mentor.objects.get(id=mentor_id)

        for sid in students_selected:
            student = Student.objects.get(id=sid)
            student.mentor = mentor
            student.save()

        messages.success(request, "Bulk mentor assignment successful!")
        return redirect("tpo_dashboard")

    return redirect("tpo_dashboard")

@login_required
def export_students_csv(request):

    if request.user.profile.user_type != "tpo":
        return redirect("home")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=students.csv"

    writer = csv.writer(response)
    writer.writerow(["Name", "Branch", "Mentor", "CGPA", "Placement Status"])

    students = Student.objects.all()

    for s in students:
        status = (
            "Placed" if s.placements.filter(status="Accepted").exists()
            else "In Progress" if s.placements.exists()
            else "Not Placed"
        )
        writer.writerow([s.name, s.branch, s.mentor, s.cgpa, status])

    return response

# @login_required
# def tpo_placements(request):

#     if request.user.profile.user_type != "tpo":
#         return redirect("home")

#     placements = Placement.objects.select_related("student")

#     status = request.GET.get("status")
#     if status and status != "all":
#         placements = placements.filter(status=status)

#     context = { "placements": placements }
#     return render(request, "tpo_placements.html", context)

@login_required
def tpo_placements(request):
    # Only TPO
    if not hasattr(request.user, "profile") or request.user.profile.user_type != "tpo":
        return redirect("home")

    # Base queryset and annotate numeric package in LPA for sorting/aggregation
    package_in_lpa_expr = Case(
        When(package_unit='LPA', then=F('package')),
        When(package_unit='K', then=ExpressionWrapper(F('package') / Value(100.0), output_field=FloatField())),
        default=Value(0),
        output_field=FloatField()
    )

    placements = Placement.objects.select_related("student").annotate(
        package_lpa=package_in_lpa_expr
    )

    # Filters
    status = request.GET.get("status")
    branch = request.GET.get("branch")
    q = request.GET.get("q")  # search query
    sort = request.GET.get("sort", "-date")  # default sort: newest

    if status and status != "all":
        placements = placements.filter(status=status)

    if branch and branch != "all":
        placements = placements.filter(student__branch=branch)

    if q:
        q = q.strip()
        placements = placements.filter(
            Q(student__name__icontains=q) |
            Q(student__email__icontains=q) |
            Q(company__icontains=q) |
            Q(position__icontains=q)
        )

    # Sorting
    # Allowed sort values: package_desc, package_asc, date_desc, date_asc, company_asc, company_desc
    if sort == "package_desc":
        placements = placements.order_by("-package_lpa", "-created_at")
    elif sort == "package_asc":
        placements = placements.order_by("package_lpa", "-created_at")
    elif sort == "date_asc":
        placements = placements.order_by("created_at")
    elif sort == "company_asc":
        placements = placements.order_by("company")
    elif sort == "company_desc":
        placements = placements.order_by("-company")
    else:  # default: newest first
        placements = placements.order_by("-created_at")

    # Pagination
    page = request.GET.get("page", 1)
    per_page = 15
    paginator = Paginator(placements, per_page)
    try:
        placements_page = paginator.page(page)
    except PageNotAnInteger:
        placements_page = paginator.page(1)
    except EmptyPage:
        placements_page = paginator.page(paginator.num_pages)

    # Stats
    total_students = Student.objects.count()
    placed = Placement.objects.filter(status="Accepted").values("student").distinct().count()
    in_progress = Placement.objects.filter(status="Pending").values("student").distinct().count()
    avg_cgpa = round(Student.objects.aggregate(avg=Avg("cgpa"))["avg"] or 0, 2)

    # Highest package across placements (using annotated package_lpa)
    highest_package_obj = placements.order_by("-package_lpa").first()
    highest_package = highest_package_obj.package_lpa if highest_package_obj else 0

    # Top companies (for chart)
    top_companies_qs = placements.values("company").annotate(cnt=Count("id")).order_by("-cnt")[:8]
    top_companies = [{"company": x["company"] or "Unknown", "count": x["cnt"]} for x in top_companies_qs]

    # Package distribution buckets (in LPA)
    buckets = {
        "<3": 0,
        "3-6": 0,
        "6-10": 0,
        "10+": 0
    }
    for p in placements:
        val = p.package_lpa or 0
        if val < 3:
            buckets["<3"] += 1
        elif val < 6:
            buckets["3-6"] += 1
        elif val < 10:
            buckets["6-10"] += 1
        else:
            buckets["10+"] += 1

    # Distinct branches for filter dropdown
    branches = Student.objects.values_list("branch", flat=True).distinct()

    # Build context
    context = {
        "placements": placements_page,        # paginated page
        "raw_placements_count": placements.count(),  # count after filters
        "total_students": total_students,
        "placed": placed,
        "in_progress": in_progress,
        "avg_cgpa": avg_cgpa,
        "highest_package": round(highest_package, 2),
        "top_companies_json": json.dumps(top_companies),
        "buckets_json": json.dumps(buckets),
        "branches": branches,
        "paginator": paginator,
        "page_obj": placements_page,
        "query_params": request.GET.urlencode(),  # helpful to preserve
        "current_filters": {
            "status": status or "all",
            "branch": branch or "all",
            "q": q or "",
            "sort": sort or ""
        }
    }

    return render(request, "tpo_placements.html", context)


@login_required
def export_placements_csv(request):
    # Only TPO
    if not hasattr(request.user, "profile") or request.user.profile.user_type != "tpo":
        return redirect("home")

    # Build same queryset as in tpo_placements so export respects filters
    package_in_lpa_expr = Case(
        When(package_unit='LPA', then=F('package')),
        When(package_unit='K', then=ExpressionWrapper(F('package') / Value(100.0), output_field=FloatField())),
        default=Value(0),
        output_field=FloatField()
    )

    placements = Placement.objects.select_related("student").annotate(package_lpa=package_in_lpa_expr)

    status = request.GET.get("status")
    branch = request.GET.get("branch")
    q = request.GET.get("q")

    if status and status != "all":
        placements = placements.filter(status=status)
    if branch and branch != "all":
        placements = placements.filter(student__branch=branch)
    if q:
        placements = placements.filter(
            Q(student__name__icontains=q) |
            Q(student__email__icontains=q) |
            Q(company__icontains=q) |
            Q(position__icontains=q)
        )

    # Build response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=placements_export.csv"

    writer = csv.writer(response)
    writer.writerow(["Student Name", "Email", "Branch", "Company", "Position", "Package (raw)", "Unit", "Package (LPA)", "Status", "Created At"])

    for p in placements.order_by("-created_at"):
        writer.writerow([
            p.student.name,
            p.student.email,
            p.student.branch,
            p.company,
            p.position,
            p.package,
            p.package_unit,
            round(p.package_lpa or 0, 2),
            p.status,
            p.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])

    return response

