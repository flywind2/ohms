"""
OHMS: Online Homework Management System
"""

import os
from flask import Flask, request, render_template, make_response
import json
from utils import NewEncoder
from datetime import datetime, timedelta

from base import session
from objects import Question, QuestionResponse, ItemResponse, QuestionGrade, User
from queries import get_user, get_homework, get_question, \
    get_question_response, get_question_responses, \
    get_question_grade, get_question_grades, \
    get_grading_permissions, set_grading_permissions, \
    get_grading_task, get_grading_tasks_for_grader, get_grading_tasks_for_response, \
    get_sample_responses
import options


# Configuration based on deploy target
if options.target == "local":
    app = Flask(__name__, static_url_path="/static", static_folder="../static")
    sunet = "test"
    user = User(sunet=sunet,
                name="Test User",
                type="admin",
                group=0)
else:
    app = Flask(__name__)
    app.debug = (options.target != "prod")
    sunet = os.environ.get("WEBAUTH_USER")
    if not sunet:
        raise Exception("You are no longer logged in. Please refresh the page.")
    try:
        user = get_user(sunet)
    except:
        user = User(sunet=sunet,
                    name=os.environ.get("WEBAUTH_LDAP_DISPLAYNAME"),
                    type="student")
        session.add(user)
        session.commit()

treatments = {
    0: [None,1,None,1,None,1,None,0,None,0,None,1,None,1,None,0,None,0],
    1: [None,1,None,0,None,0,None,1,None,1,None,0,None,0,None,1,None,1],
    2: [None,1,None,1,None,1,None,0,None,0,None,0,None,0,None,1,None,1],
    3: [None,1,None,0,None,0,None,1,None,1,None,1,None,1,None,0,None,0]
    }

@app.route("/")
def index():
    hws = get_homework()
    
    if user.group is not None:
        peer_grading = treatments[user.group]
    elif user.type == "admin" or user.type == "grader":
        peer_grading = [None,1]*int(round(.5*len(hws)))
    else:
        peer_grading = [None,-1]*int(round(.5*len(hws)))

    from collections import defaultdict
    todo = defaultdict(int)
    questions = session.query(Question).all()
    for q in questions:

        responses = get_question_responses(q.id, user.sunet)

        if responses:
            r = responses[-1]
            tasks = get_grading_tasks_for_response(r.id)

            # ignore if this is not a peer graded question
            if not tasks:
                continue

            # if user has no score for response, compute score if peer grades due
            if r.score is None:
                permission = get_grading_permissions(q.id, tasks[0].grader)
                if permission.due_date < datetime.now():
                    scores = []
                    for task in tasks:
                        submits = get_question_grades(task.id)
                        if submits: scores.append(submits[-1].score)
                    if scores:
                        r.score = sorted(scores)[len(scores) // 2] # median
                        session.commit()

            # check if user has any ratings to complete
            else:
                for task in tasks:
                    submits = get_question_grades(task.id)
                    if submits and not submits[-1].rating:
                        todo[q.homework.name] += 1

    grades = []
    try:
        f = open('/afs/ir/class/psych10/grades/grades.csv')
        reader = __import__('csv').reader(f)
        headers = reader.next()[1:]
        for row in reader:
            if row[0] == user.sunet:
                grades = zip(*(headers, row[1:]))
    except:
        pass

    return render_template("index.html", homeworks=hws,
                           peer_grading=peer_grading,
                           user=user,
                           options=options,
                           current_time=datetime.now(),
                           grades=grades,
                           todo=todo
    )


@app.route("/hw", methods=['GET'])
def hw():
    hw_id = request.args.get("id")
    homework = get_homework(hw_id)
    if user.type != "admin" and homework.start_date and homework.start_date > datetime.now():
        raise Exception("This homework has not yet been released.")
    else:
        return render_template("hw.html",
                               homework=homework,
                               user=user,
                               options=options)


@app.route("/grade", methods=['GET'])
def grade():
    hw_id = request.args.get("id")
    homework = get_homework(hw_id)
    permissions = []
    for q in homework.questions:
        try:
            permissions.append(get_grading_permissions(q.id, sunet))
        except:
            pass
    questions = []
    for permission in permissions:
        question = permission.question
        if permission.permissions:
            tasks = get_grading_tasks_for_grader(question.id, sunet)
        else:
            qrs = get_sample_responses(question.id)
            tasks = [{"id": qr.id, "question_response": qr} for qr in qrs]

        questions.append({
            "question": question,
            "permission": permission.permissions,
            "tasks": tasks})

    return render_template("grade.html",
                           homework=homework,
                           questions=questions,
                           user=user,
                           options=options)


@app.route("/rate", methods=['GET'])
def rate():

    out = {}
    question_response_id = request.args.get("id")

    # check that student is the one who submitted this QuestionResponse

    question_response = get_question_response(question_response_id)
    if question_response.sunet != sunet and user.type != "admin":
        raise Exception("You are not authorized to rate this response.")

    # fetch all peers that were assigned to grade this QuestionResponse
    grading_tasks = get_grading_tasks_for_response(question_response_id)
    question_grades = []
    for task in grading_tasks:
        submissions = get_question_grades(task.id)
        if submissions:
            question_grades.append(submissions[-1])

    return render_template("rate.html", 
                           question_grades=question_grades,
                           options=options)


def check_if_locked(due_date, submissions):
    past_due = due_date and due_date < datetime.now()
    return past_due
    # if len(submissions) > 1:
    #     last_time = max(x.time for x in submissions)
    #     too_many_submissions = datetime.now() < last_time + timedelta(hours=6)
    # else:
    #     too_many_submissions = False
    # return past_due or too_many_submissions


@app.route("/load", methods=['GET'])
def load():

    out = {}
    q_id = request.args.get("q_id")

    # if loading a student response to a question
    if q_id[0] == "q":
        question_id = q_id[1:]
        question = get_question(question_id)
        submissions = get_question_responses(question_id, sunet)
        out['submission'] = submissions[-1] if submissions else None
        out['locked'] = check_if_locked(question.hw.due_date, submissions)
        if datetime.now() > question.hw.due_date:
            out['solution'] = [item.solution for item in question.items]

    # if loading a student's peer grade for an actual student's response
    elif q_id[0] == "g":
        grading_task_id = q_id[1:]
        question_grades = get_question_grades(grading_task_id)
        if question_grades:
            question_id = question_grades[0].grading_task.question_response.question_id
        else:
            question_id = get_grading_task(grading_task_id).question_response.question_id
        if question_grades:
            out['submission'] = {
                "time": datetime.now(),
                "item_responses": [
                    {"response": question_grades[-1].score},
                    {"response": question_grades[-1].comments}
                    ]
                }
        permission = get_grading_permissions(question_id, sunet)
        out['locked'] = (datetime.now() > permission.due_date)

    # if loading a student's scores for a sample response (not currently functional)
    elif q_id[0] == "s":
        question_id = q_id[1:]
        permission = get_grading_permissions(question_id, sunet)
        out['locked'] = (datetime.now() > permission.due_date)

    # if loading a student rating to a peer grade
    elif q_id[0] == "r":
        question_grade_id = q_id[1:]
        question_grade = get_question_grade(question_grade_id)
        if question_grade.rating:
            out['submission'] = {
                "item_responses": [ {"response": question_grade.rating} ]
                }
        out['locked'] = False

    return json.dumps(out, cls=NewEncoder)


@app.route("/submit", methods=['POST'])
def submit():
    q_id = request.args.get("q_id")
    submit_type = q_id[0]
    id = q_id[1:]

    responses = request.form.getlist('responses')

    question_response = QuestionResponse(
        sunet=sunet,
        time=datetime.now(),
        question_id=id
    )

    # Question submission
    if submit_type == "q":
        submissions = get_question_responses(id, sunet)
        question = submissions[0].question if submissions else get_question(id)

        is_locked = check_if_locked(question.hw.due_date, submissions)

        if not is_locked:

            score, comments = question.check(responses)

            question_response.score = score
            question_response.comments = comments
            for item, response in zip(question.items, responses):
                item_response = ItemResponse(item_id=item.id,
                                             response=response)
                question_response.item_responses.append(item_response)

            # add response to the database
            session.add(question_response)
            session.commit()

            submissions.append(question_response)
            is_locked = check_if_locked(question.hw.due_date, submissions)

        else:
            raise Exception("The deadline for submitting this homework has passed.")

    # Sample question grading submission
    elif submit_type == "s":
        is_locked = False

        sample_responses = get_sample_responses(id)

        assigned_scores = [float(resp) for resp in responses]
        true_scores = [float(resp.score) for resp in sample_responses]

        if assigned_scores == true_scores:
            set_grading_permissions(id, sunet, 1)
            summary_comment = '''
<p>Congratulations! You are now
qualified to grade this question. Please refresh the 
page to see the student responses.</p>'''
        else:
            summary_comment = '''
<p>Sorry, but there's a discrepancy between your score and the 
instructor scores for these sample responses. Please try again.</p>'''

        summary_comment += '''
<p>Instructor comments for each response should now appear 
above. They are intended to help you determine why each response earned 
the score it did.</p>'''

        question_response.comments = [r.comments for r in sample_responses]
        question_response.comments.append(summary_comment)


    # Grading student questions
    elif submit_type == "g":
        is_locked = False

        # Make sure student was assigned this grading task
        task = get_grading_task(id)
        if task.grader != sunet:
            raise Exception("You are not authorized to grade this response.")
            
        try:
            score = float(responses[0])
        except:
            raise Exception("Sorry, I didn't understand the score you entered. Please check that you have entered a score.")
        comments = responses[1]

        question_grade = QuestionGrade(
            grading_task=task,
            time=datetime.now(),
            score=score,
            comments=comments
        )
        session.add(question_grade)
        session.commit()

        question_response.comments = "Your scores have been "\
            "successfully recorded!"

    # Rating the peer reviews
    elif submit_type == "r":
        is_locked = False

        # Make sure student was assigned to rate this
        rating = request.form.getlist('responses')[0]
        question_grade = get_question_grade(id)
        if question_grade.grading_task.question_response.sunet == sunet:
            question_grade.rating = rating
            session.commit()
        else:
            raise Exception("You are not authorized to rate this grade.")

        question_response.comments = "Rating submitted successfully!"
        

    # Wrong submit_type
    else:
        raise Exception("Invalid submission.")

    # add response to what to return to the user
    return json.dumps({
        "locked": is_locked,
        "submission": question_response,
    }, cls=NewEncoder)



@app.route("/staff")
def staff():
    return render_template("office_hours.html", options=options, user=user)

@app.route("/handouts")
def handouts():
    handouts = sorted(os.listdir("/afs/ir/%s/WWW/handouts" % options.class_prefix))
    return render_template("handouts.html", handouts=handouts, options=options, user=user)

@app.route("/tips")
def tips():
    return render_template("tips.html", options=options, user=user)

@app.route("/grading")
def grading():
    return render_template("grading.html", options=options, user=user)

@app.errorhandler(Exception)
def handle_exceptions(error):
    return make_response(error.message, 403)


# For local development--this does not run in prod or test
if __name__ == "__main__":
    app.run(debug=True)
