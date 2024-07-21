import calendar
import json
import os
import re
from dateutil import parser
import threading
import time
from datetime import date, datetime, timedelta
from io import BytesIO
from multiprocessing import context
from threading import Thread
import boto3
import pandas as pd
import razorpay
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Max, Q
from django.db.models.fields import UUIDField
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import HttpResponse, get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.html import strip_tags
from forex_python.converter import CurrencyRates
from xhtml2pdf import pisa

from blockchain.contractInteraction import fetchFromBlockchain
from blockchain.contractInteraction import verifyFromBlockchain
from blockchain.decryptIPFS import ipfsUriDecrypt
from blockchain.submitIPFS import upload_to_ipfs
from lpp.models import MNFLPPDDatabase
from MNF.settings import COUNTRY_KEY, EMAIL_HOST_USER, BasePath
from mnfapp.models import Author, PaymentData, PitchVector, SampleScript, centralDatabase
from page_script.models import MNFScriptDatabase_2
from page_script.views import script_id_generator
from payment.models import privilegedUser1
from relationshipmanager.models import RMDatabase

from .models import *
from .utils import render_to_pdf
from utils.scripts_functions import script_upload

from functools import lru_cache

stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_PUB_KEY = settings.STRIPE_PUBLISHABLE_KEY
# keyID = settings.RAZORPAY_KEY_ID
# keySecret = settings.RAZORPAY_KEY_SECRET
UsdConversionRate = 80


def set_payment_token(request):
    if request.user.is_superuser:
        request.session["keyID"] = settings.T_RAZORPAY_KEY_ID
        request.session["keySecret"] = settings.T_RAZORPAY_KEY_SECRET
    else:
        request.session["keyID"] = settings.RAZORPAY_KEY_ID
        request.session["keySecret"] = settings.RAZORPAY_KEY_SECRET

# from celery.schedules import crontab
# from celery.task import periodic_task


basepath = BasePath()
per_page = 10
mybid_per_page = 10
showroom_per_page = 10
commission_per_page = 10
auction_pages = 10
my_auction_pages = 10
premises_per_page = 10
sameauction_pages = 10


class sendemail(threading.Thread):
    def __init__(self, whomtosend, titleofmail, dateofemail, context, EMAIL_HOST_USER):
        self.whomtosend = whomtosend
        self.titleofmail = titleofmail
        self.dateofemail = dateofemail
        self.context = context
        self.EMAIL_HOST_USER = EMAIL_HOST_USER
        threading.Thread.__init__(self)

    def run(self):
        print("run self class", self.context)
        subject = str(self.titleofmail) + " " + str(self.dateofemail) + "."
        from_email = self.EMAIL_HOST_USER
        to = self.whomtosend

        html_content = render_to_string(
            rf"{basepath}/ideamall/templates/ideamall/email_templete.html",
            self.context,  # /home/user/mnf/project/MNF/ideamall/templates/ideamall/email_templete.html
        )  # render with dynamic value
        # Strip the html tag. So people can see the pure text at least.
        text_content = strip_tags(html_content)
        # create the email, and attach the HTML version as well.
        msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
        msg.attach_alternative(html_content, "text/html")
        msg.send()


def sendemailim(whomtosend, titleofmail, dateofemail, context):
    subject = str(titleofmail) + " " + str(dateofemail) + "."
    from_email = settings.EMAIL_HOST_USER
    to = whomtosend

    html_content = render_to_string(
        rf"{basepath}/ideamall/templates/ideamall/email_templete.html",
        context,  # /home/user/mnf/project/MNF/ideamall/templates/ideamall/email_templete.html
    )  # render with dynamic value
    # Strip the html tag. So people can see the pure text at least.
    text_content = strip_tags(html_content)
    # create the email, and attach the HTML version as well.
    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
    msg.attach_alternative(html_content, "text/html")
    msg.send()
    return True


def payment(currency, status, reserveprize, startdate, enddate, filesize):

    print("Currency conversion: ", str(currency.upper()))

    with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
        curr = json.load(c)

        print(curr["rates"]["INR"])
        failed_curr = []
        try:
            rate = curr["rates"][str(currency.upper())]
            print(rate, " : Latest rates 30sep")
            # c = CurrencyRates()
            # rate = c.get_rate("USD", str(currency.upper()))
        except Exception as e:
            failed_curr.append(str(e))
            rate = 80

    reserveprize = float(reserveprize) / rate

    filesize = filesize / pow(1024, 3)
    rate = filesize * 10
    if status == "Project Completed":
        percent = 3
    elif status == "Part Shoot completed":
        percent = 2
    elif status == "Star Cast Locked":
        percent = 1
    totalrate = rate
    enddate = datetime.strptime(enddate, "%Y-%m-%d")
    startdate = datetime.strptime(startdate, "%Y-%m-%d")
    left_date = enddate - startdate
    removetime = left_date.days
    while removetime > 0:
        rates = (percent * reserveprize) / 100
        totalrate += rates
        removetime -= 30
    if round(totalrate, 3) < 0.060:
        totalrate = 0.060

    return round(totalrate, 2)


def commissionpayment(currency, duration, status, will_to_pay, total_script, send_mail):

    # c = CurrencyRates()
    # rate = c.get_rate("USD", str(currency))
    with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
        curr = json.load(c)

        print(curr["rates"]["INR"])

        try:
            rate = curr["rates"][str(currency.upper())]
            print(rate, " : Latest rates 30sep")
            # c = CurrencyRates()
            # rate = c.get_rate("USD", str(currency.upper()))
        except:
            rate = 80

    will_to_pay = float(will_to_pay) / rate

    totalrate = 0
    if send_mail == "True":
        totalrate += duration * 0.2
    if total_script == "One":
        totalrate += 1
    elif total_script == "More than one":
        totalrate += 3
    if status == "One Pager Ready":
        totalrate += 0.03 * float(will_to_pay)
    elif status == "Logline Final":
        totalrate += 0.025 * float(will_to_pay)
    elif status == "Idea Final":
        totalrate += 0.02 * float(will_to_pay)
    elif status == "Premise Value":
        totalrate += 0.015 * float(will_to_pay)
    elif status == "Only Subject Final":
        totalrate += 0.01 * float(will_to_pay)
    if round(totalrate, 3) < 0.060:
        totalrate = 0.060
    return round(totalrate, 2)


def auctionCheckout(request):
    set_payment_token(request)
    keyID = request.session["keyID"]
    keySecret = request.session["keySecret"]
    # print(funcname)
    if request.method == "POST":

        total_amount = request.session["total_amount"]

        # try:
        #     c = CurrencyRates()
        #     rate = c.get_rate("USD", "INR")

        # except Exception as e:
        #     print("checkout error", e)
        #     rate = 80
        with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
            curr = json.load(c)

            print(curr["rates"]["INR"])

            try:
                rate = curr["rates"]["INR"]
                print(rate, " : Latest rates 30sep")
                # c = CurrencyRates()
                # rate = c.get_rate("USD", str(currency.upper()))
            except Exception as e:
                print("checkout error", e)
                rate = 80

        amtINR = round((float(total_amount) * rate), 2)

        print("pitamtch:", total_amount, type(total_amount))
        if request.POST.get("country") == "IN":
            client = razorpay.Client(auth=(keyID, keySecret))

            print("thisistherate::", rate)
            # amtINR = round(float(float(total_amount) * rate), 2)
            print("pitamtINRr:", amtINR)
            try:
                payment_intent = client.order.create(
                    {
                        "amount": int(float(total_amount) * 100 * rate),
                        "currency": "INR",
                        "payment": {
                            "capture": "automatic",
                            "capture_options": {"refund_speed": "normal"},
                        },
                    }
                )
            except:
                return redirect("auction_full_failed")
            pid = payment_intent["id"]
            return render(
                request,
                "ideamall/checkoutN_RazorPay.html",
                {"pk": keyID, "amtINR": amtINR, "pid": pid, "amount": total_amount},
            )
        else:

            customer = stripe.Customer.create(
                email=request.user.email,
            )
            payment_intent = stripe.PaymentIntent.create(
                amount=int(float(total_amount) * 100 * rate),
                currency="INR",
                automatic_payment_methods={"enabled": True},
                customer=customer.id,
            )
            pid = payment_intent.id
            request.session["payment_intent_id"] = pid
            context = {
                "pid": pid,
                "amtINR": amtINR,
                "secret_key": payment_intent.client_secret,
                "total_amount": total_amount,
                "STRIPE_PUBLISHABLE_KEY": STRIPE_PUB_KEY,
                "pk": STRIPE_PUB_KEY,
            }
            return render(request, "ideamall/checkoutNnew.html", context)
    return render(request, "ideamall/showcase.html")


@login_required
def paymentDoneauction_RazorPay(request):
    keyID = request.session["keyID"]
    keySecret = request.session["keySecret"]
    try:
        razorpay_order_id = request.POST["razorpay_order_id"]
        razorpay_payment_id = request.POST["razorpay_payment_id"]
        razorpay_signature = request.POST["razorpay_signature"]
        client = razorpay.Client(auth=(keyID, keySecret))
        params_dict = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        }
        try:
            client.utility.verify_payment_signature(params_dict)
        except:
            user = request.user
            email = user.email
            message = render_to_string("ideamall/failmail.html")
            email_message = EmailMessage(
                "Something really went wrong",
                message,
                settings.EMAIL_HOST_USER,
                [email],
            )

        # try:

        #     c = CurrencyRates()
        #     rate = c.get_rate("USD", "INR")
        # except Exception as e:
        #     print("some", e)
        #     rate = 80
        with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
            curr = json.load(c)

            print(curr["rates"]["INR"])

            try:
                rate = curr["rates"]["INR"]
                print(rate, " : Latest rates 30sep")
                # c = CurrencyRates()
                # rate = c.get_rate("USD", str(currency.upper()))
            except Exception as e:
                print("checkout error", e)
                rate = 80

        total_amount = round(
            float((request.session["total_amount"]) * rate), 2)
        paydetail = client.payment.fetch(razorpay_payment_id)
        user_id = request.user
        payment_id = razorpay_payment_id

        gateway_fee = paydetail["fee"] / 100  # to convert from paise to rupees
        currency = paydetail["currency"]
        pay_method = paydetail["method"]
        services_used = "auction-full-rights"
        payment_status = "Success"
        payment_gateway = "RazorPay"

        PaymentData.objects.create(
            user_id=user_id,
            payment_id=payment_id,
            services_used=services_used,
            total_amount=total_amount,
            gateway_fee=gateway_fee,
            currency=currency,
            pay_method=pay_method,
            payment_status=payment_status,
            payment_gateway=payment_gateway,
        )
        return redirect("auction_success")
    except:
        return redirect("auction_full_failed")


@login_required
def paymentDoneauction_stripe(request):
    try:
        payment_intent_id = request.session["payment_intent_id"]
        print("In payment done::::,,", payment_intent_id)
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        if pi.status == "succeeded":

            # -----------Adding Details to payment Details--------------------------

            # c = CurrencyRates()
            # rate = c.get_rate("USD", "INR")
            with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
                curr = json.load(c)

                print(curr["rates"]["INR"])

                try:
                    rate = curr["rates"]["INR"]
                    print(rate, " : Latest rates 30sep")
                    # c = CurrencyRates()
                    # rate = c.get_rate("USD", str(currency.upper()))
                except Exception as e:
                    print("checkout error", e)
                    rate = 80

            total_amount = round(
                float((request.session["total_amount"]) * rate), 2)
            user_id = request.user
            payment_id = pi["id"]
            amount_charged = total_amount
            gateway_fee = pi["application_fee_amount"]
            currency = pi["currency"]
            pay_method = "Card"
            services_used = "auction-full-rights"
            payment_status = "Success"
            payment_gateway = "Stripe"
            PaymentData.objects.create(
                user_id=user_id,
                services_used=services_used,
                pay_method=pay_method,
                payment_id=payment_id,
                total_amount=total_amount,
                amount_charged=amount_charged,
                gateway_fee=gateway_fee,
                payment_gateway=payment_gateway,
                currency=currency,
                payment_status=payment_status,
            )
            return redirect("auction_success")
        else:
            return redirect("auction_full_failed")
    except:
        return redirect("auction_full_failed")


def commssioningpage(request):
    if request.method == "POST":
        x = Commissioning()
        x.commission_string = str(time.time()) + "-commission"
        print("Unique string: ", x.commission_string)
        duration_final = 0
        x.user_id = request.user
        x.projectname = request.POST.get("projectname")
        x.proposedtype = request.POST.get("proposedtype")
        if request.POST.get("episodes"):
            x.no_episodes = request.POST.get("episodes")
        if request.POST.get("duration_episodes"):
            x.duration_episodes = request.POST.get("duration_episodes")
            duration_final += int(x.duration_episodes) * int(x.no_episodes)
        x.please_describe = request.POST.get("describe")
        if request.POST.get("duration"):
            x.duration = request.POST.get("duration")
            duration_final += int(x.duration)
        elif request.POST.get("duration1"):
            x.duration = request.POST.get("duration1")
            duration_final += int(x.duration)
        else:
            pass
        x.currentstatus = request.POST.get("currentstatus")
        x.commission_negotiable = request.POST.get("negotiation")
        x.logline = request.POST.get("logline")
        x.genre = request.POST.get("genre")
        x.subgenre = request.POST.get("subgenre")
        x.languagedialogues = request.POST.get("languagedialogues")
        x.scriptdialogues = request.POST.get("scriptdialogues")
        x.languagescreenplay = request.POST.get("languagescreenplay")
        x.scriptscreenplay = request.POST.get("scriptscreenplay")
        x.dateofcommissioning = date.today()
        x.scriptdate = request.POST.get("scriptdate")
        x.deadlineflexibleby = request.POST.get("deadlineflexibleby")
        x.months_year_date = request.POST.get("time")
        x.buggetincurrency = request.POST.get("buggetincurrency")
        x.buggetinamount = request.POST.get("buggetinamount")
        x.payforassignmentcurrency = request.POST.get(
            "payforassignmentcurrent")
        x.payforassignmentamount = request.POST.get("payforassignmentamount")
        x.paymentincreaseby = request.POST.get("paymentincreaseby")
        x.onsigning = request.POST.get("onsigning")
        x.boundscript = request.POST.get("boundscript")
        x.scriptlocking = request.POST.get("scriptlocking")
        x.filmrelease = request.POST.get("filmrelease")
        x.bonus = request.POST.get("bonus")
        x.howmanyscriptpurchased = request.POST.get("howmanyscriptpurchased")
        x.highestamountpaidcurrency = request.POST.get(
            "highestamountpaidcurrency")

        if request.POST.get("highestamount"):
            x.highestamountpaidamount = request.POST.get("highestamount")
        else:
            x.highestamountpaidamount = 0

        if x.howmanyscriptpurchased == "None":
            x.comm_credibility = 0
        elif x.howmanyscriptpurchased == "One":
            x.comm_credibility = 1
        else:
            x.comm_credibility = 2

        if request.POST.get("highestamount"):
            if x.highestamountpaidamount == 0:
                pass
            elif (
                int(x.highestamountpaidamount) > 0
                and int(x.highestamountpaidamount) <= 30
            ):
                x.comm_credibility += 1
            elif (
                int(x.highestamountpaidamount) > 30
                and int(x.highestamountpaidamount) <= 300
            ):
                x.comm_credibility += 2
            elif (
                int(x.highestamountpaidamount) > 300
                and int(x.highestamountpaidamount) <= 3000
            ):
                x.comm_credibility += 3
            elif (
                int(x.highestamountpaidamount) > 3000
                and int(x.highestamountpaidamount) <= 30000
            ):
                x.comm_credibility += 4
            elif (
                int(x.highestamountpaidamount) > 30000
                and int(x.highestamountpaidamount) <= 300000
            ):
                x.comm_credibility += 5
            else:
                x.comm_credibility += 6

        if request.POST.get("publishmyproject"):
            x.publicise_my_project = True
            lpp = MNFLPPDDatabase.objects.filter(
                firstLanguage=x.languagedialogues
            ).filter(secondLanguage=x.languagedialogues)
            for i in lpp:
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": i.lpp_email,
                    "emailcode": "IM40",
                    "heading1": "OPPORTUNITY!",
                    "heading2": "An script writing assignment in "
                    + str(x.languagedialogues)
                    + " is waiting for you!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemail(
                    i.lpp_email,
                    "new opportunity",
                    date.today(),
                    context_email,
                    EMAIL_HOST_USER,
                ).start()
            rm = RMDatabase.objects.filter(motherTongue=x.languagedialogues).filter(
                secondSpokenLang=x.languagedialogues
            )
            for i in rm:
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": i.user_id.email,
                    "emailcode": "IM40",
                    "heading1": "OPPORTUNITY!",
                    "heading2": "An script writing assignment in "
                    + str(x.languagedialogues)
                    + " is waiting for you!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemail(
                    i.user_id.email,
                    "new opportunity",
                    date.today(),
                    context_email,
                    EMAIL_HOST_USER,
                ).start()
            lm = privilegedUser1.objects.filter(memberType="Life Member")
            for i in lm:
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": i.user.email,
                    "emailcode": "IM40",
                    "heading1": "OPPORTUNITY!",
                    "heading2": "An script writing assignment in "
                    + str(x.languagedialogues)
                    + " is waiting for you!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemail(
                    i.user.email,
                    "new opportunity",
                    date.today(),
                    context_email,
                    EMAIL_HOST_USER,
                ).start()
        if request.POST.get("alreadywrittenscript"):
            x.choice_lang_scripts = True
            t = Showcase.objects.filter(
                projectstatus="Entire Script Ready", genre=x.genre, subgenre=x.subgenre
            ).exclude(user_id=request.user)
            for i in t:
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": i.user_id.email,
                    "emailcode": "IM41",
                    "heading1": "OPPORTUNITY!",
                    "heading2": str(i.projecttitle)
                    + " has a seeker in "
                    + str(x.languagedialogues)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemail(
                    i.user_id.email,
                    "ready buyer for different language",
                    date.today(),
                    context_email,
                    EMAIL_HOST_USER,
                ).start()
        if request.POST.get("scriptupforauction"):
            x.irrespective_project_status = True
            # subject = "Script up for Auction " + "."
            # datas = Auction.objects.filter(auction_details.languagedialogues=x.languagedialogues,
            #                                auction_details.genre=x.genre,
            #                                auction_details.subgenre=x.subgenre).exclude(user_id=request.user)
            # for data in datas:
            #     with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            #         body = f.read()

            #     context_email = {
            #         "Date": date.today(),
            #         "Name": data.user_id.email,
            #         "emailcode": "IM42",
            #         "heading1": "OPPORTUNITY!",
            #         "heading2": str(data.auction_details.projecttitle)
            #         + " has a ready buyer!!",
            #         "body": body,
            #     }
            #     # whomtosend, titleofmail, dateofemail, context\
            #     sendemailim(
            #         data.user_id.email,
            #         "ready buyer availavle",
            #         date.today(),
            #         context_email,
            #     )
        commission_amount = commissionpayment(
            x.buggetincurrency,
            duration_final,
            x.currentstatus,
            x.payforassignmentamount,
            x.howmanyscriptpurchased,
            x.publicise_my_project,
        )
        print(commission_amount, " : commission_amount")

        x.save()
        
        # store data in centraldatabase
        cd = centralDatabase.objects.get(user_id=request.user)
        cd.project_title = x.projectname
        cd.project_type = x.proposedtype
        cd.project_status = x.currentstatus
        cd.genre = x.genre
        cd.subgenre = x.subgenre
        cd.logline = x.logline
        cd.language = x.languagedialogues
        cd.language_of_screenplay = x.languagescreenplay
        cd.budget_currency = x.buggetincurrency
        cd.budget_amount = x.buggetinamount
        cd.save()
        

        request.session["commission_string"] = x.commission_string
        request.session["comm_amount"] = commission_amount

        context = {
            "projectname": x.projectname,
            "proposedtype": x.proposedtype,
            "duration": x.duration,
            "currentstatus": x.currentstatus,
            "genre": x.genre,
            "languagedialogues": x.languagedialogues,
            "amount": commission_amount,
        }
        return render(request, "ideamall/comm_checkout.html", context)

    return render(request, "ideamall/commssioningpage.html")


def commissionCheckout(request):
    set_payment_token(request)
    keyID = request.session["keyID"]
    keySecret = request.session["keySecret"]
    if request.method == "POST":

        total_amount = request.session["comm_amount"]

        # try:
        #     c = CurrencyRates()
        #     rate = c.get_rate("USD", "INR")

        # except Exception as e:
        #     print("checkout error", e)
        #     rate = 80
        with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
            curr = json.load(c)

            print(curr["rates"]["INR"])

            try:
                rate = curr["rates"]["INR"]
                print(rate, " : Latest rates 30sep")
                # c = CurrencyRates()
                # rate = c.get_rate("USD", str(currency.upper()))
            except Exception as e:
                print("checkout error", e)
                rate = 80

        amtINR = round((float(total_amount) * rate), 2)

        print("pitamtch:", total_amount, type(total_amount))
        if request.POST.get("country") == "IN":
            client = razorpay.Client(auth=(keyID, keySecret))

            print("thisistherate::", rate)
            # amtINR = round(float(float(total_amount) * rate), 2)
            print("pitamtINRr:", amtINR)
            payment_intent = client.order.create(
                {
                    "amount": int(float(total_amount) * 100 * rate),
                    "currency": "INR",
                    "payment": {
                        "capture": "automatic",
                        "capture_options": {"refund_speed": "normal"},
                    },
                }
            )
            pid = payment_intent["id"]
            return render(
                request,
                "ideamall/checkout_comm_razor.html",
                {"pk": keyID, "amtINR": amtINR, "pid": pid, "amount": total_amount},
            )
        else:

            customer = stripe.Customer.create(
                email=request.user.email,
            )
            payment_intent = stripe.PaymentIntent.create(
                amount=int(float(total_amount) * 100 * rate),
                currency="INR",
                automatic_payment_methods={"enabled": True},
                customer=customer.id,
            )
            pid = payment_intent.id
            request.session["payment_intent_id"] = pid
            context = {
                "pid": pid,
                "amtINR": amtINR,
                "secret_key": payment_intent.client_secret,
                "total_amount": total_amount,
                "STRIPE_PUBLISHABLE_KEY": STRIPE_PUB_KEY,
                "pk": STRIPE_PUB_KEY,
            }
            return render(request, "ideamall/checkout_comm_stipe.html", context)
    return render(request, "ideamall/commssioningpage.html")


@login_required
def paymentDonecomm_stripe(request):
    try:
        payment_intent_id = request.session["payment_intent_id"]
        print("In payment done::::,,", payment_intent_id)
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        if pi.status == "succeeded":

            # -----------Adding Details to payment Details--------------------------

            # c = CurrencyRates()
            # rate = c.get_rate("USD", "INR")
            with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
                curr = json.load(c)

                print(curr["rates"]["INR"])

                try:
                    rate = curr["rates"]["INR"]
                    print(rate, " : Latest rates 30sep")
                    # c = CurrencyRates()
                    # rate = c.get_rate("USD", str(currency.upper()))
                except Exception as e:
                    print("checkout error", e)
                    rate = 80

            total_amount = round(
                float((request.session["comm_amount"]) * rate), 2)
            user_id = request.user
            payment_id = pi["id"]
            amount_charged = total_amount
            gateway_fee = pi["application_fee_amount"]
            currency = pi["currency"]
            pay_method = "Card"
            services_used = "commissioning"
            payment_status = "Success"
            payment_gateway = "Stripe"
            PaymentData.objects.create(
                user_id=user_id,
                services_used=services_used,
                pay_method=pay_method,
                payment_id=payment_id,
                total_amount=total_amount,
                amount_charged=amount_charged,
                gateway_fee=gateway_fee,
                payment_gateway=payment_gateway,
                currency=currency,
                payment_status=payment_status,
            )
            return redirect("commission_success")
        else:
            return redirect("commission_failed")
    except:
        return redirect("commission_failed")


@login_required
def paymentDonecomm_RazorPay(request):
    keyID = request.session["keyID"]
    keySecret = request.session["keySecret"]
    try:
        razorpay_order_id = request.POST["razorpay_order_id"]
        razorpay_payment_id = request.POST["razorpay_payment_id"]
        razorpay_signature = request.POST["razorpay_signature"]
        client = razorpay.Client(auth=(keyID, keySecret))
        params_dict = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        }
        try:
            client.utility.verify_payment_signature(params_dict)
        except:
            user = request.user
            email = user.email
            message = render_to_string("ideamall/failmail.html")
            email_message = EmailMessage(
                "Something really went wrong",
                message,
                settings.EMAIL_HOST_USER,
                [email],
            )
            return redirect("commission_failed")

        # try:

        #     c = CurrencyRates()
        #     rate = c.get_rate("USD", "INR")
        # except Exception as e:
        #     print("some", e)
        #     rate = 80

        with open(f"{basepath}/MNF/json_keys/conversionRates.json") as c:
            curr = json.load(c)

            print(curr["rates"]["INR"])

            try:
                rate = curr["rates"]["INR"]
                print(rate, " : Latest rates 30sep")
                # c = CurrencyRates()
                # rate = c.get_rate("USD", str(currency.upper()))
            except Exception as e:
                print("checkout error", e)
                rate = 80

        total_amount = round(float((request.session["comm_amount"]) * rate), 2)
        paydetail = client.payment.fetch(razorpay_payment_id)
        user_id = request.user
        payment_id = razorpay_payment_id

        gateway_fee = paydetail["fee"] / 100  # to convert from paise to rupees
        currency = paydetail["currency"]
        pay_method = paydetail["method"]
        services_used = "commissioning"
        payment_status = "Success"
        payment_gateway = "RazorPay"

        PaymentData.objects.create(
            user_id=user_id,
            payment_id=payment_id,
            services_used=services_used,
            total_amount=total_amount,
            gateway_fee=gateway_fee,
            currency=currency,
            pay_method=pay_method,
            payment_status=payment_status,
            payment_gateway=payment_gateway,
        )
        return redirect("commission_success")
    except:
        return redirect("commission_failed")


def commission_failed(request):
    # y = Commissioning.objects.filter(commission_id=x)
    Commissioning.objects.get(
        commission_string=request.session["commission_string"]
    ).delete()
    return render(request, "payments/failed.html")


def commission_success(request):
    x = Commissioning.objects.get(
        commission_string=request.session["commission_string"]
    )
    x.com_payment_done = True
    x.save()

    with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
        body = f.read()

    context_email = {
        "Date": date.today(),
        "Name": request.user.email,
        "emailcode": "IM39",
        "heading1": "WONDERFUL!",
        "heading2": "Your script writing assignment for "
        + str(x.projectname)
        + " is commissioned!!",
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context\
    sendemailim(
        request.user.email,
        "Idea Commissioned Successfully!",
        date.today(),
        context_email,
    )

    return redirect("mycommissionedprojects")


def mycommissionedprojects(request):
    if Commissioning.objects.filter(user_id=request.user):
        x = (
            Commissioning.objects.filter(user_id=request.user)
            .order_by("-dateofcommissioning")
            .exclude(com_payment_done=False)
        )
        # x = reversed(list(comm))
        for i in x:
            tempcount = 0
            if i.maker.all():
                for j in i.maker.all():
                    tempcount = tempcount + 1
            i.offercount = tempcount
            i.save()
        global commission_per_page
        paginate_by = request.GET.get("entries", per_page)
        commission_per_page = paginate_by
        paginator = Paginator(x, commission_per_page)
        page = request.GET.get("page")

        try:
            paginated = paginator.get_page(page)
        except PageNotAnInteger:
            paginated = paginator.get_page(1)
        except EmptyPage:
            paginated = paginator.page(paginator.num_pages)
        context = {"data": x, "page_obj": paginated}
        return render(request, "ideamall/mycommissionedprojects.html", context)
    else:
        return render(request, "ideamall/no_commission.html")


def delete_commission(request, commission_id):

    x = Commissioning.objects.get(commission_id=commission_id)
    if x.maker.all():
        for i in x.maker.all():
            i.delete()
    x.delete()
    if Commissioning.objects.filter(user_id=request.user):
        y = Commissioning.objects.filter(user_id=request.user).exclude(
            com_payment_done=False
        )
        for i in y:
            tempcount = 0
            if i.maker.all():
                for j in i.maker.all():
                    tempcount = tempcount + 1
            # count.append(tempcount)
            i.offercount = tempcount
            i.save()

        context = {"data": y}

        return render(request, "ideamall/mycommissionedprojects.html", context)
    else:
        return render(request, "ideamall/no_commission.html")


def cowritingoffers(request):
    if request.method == "POST":
        y = Showcase.objects.filter(
            findcowriter=True, languagedialogues=request.POST.get("prim_language")
        ).exclude(user_id=request.user)
        for i in y:
            print(i.genre, " : Genre cowriting")
        context = {"data": y}
        if y.count() == 0:
            context = {"alert": "alert"}
        return render(request, "ideamall/cowriter.html", context)
    return render(request, "ideamall/cowriter.html")


def cowritinglist(request):
    if request.method == "POST":
        y = Showcase.objects.filter(
            findcowriter=True, languagedialogues=request.POST.get("prim_language")
        ).exclude(user_id=request.user)
        for i in y:
            print(i.genre, " : Genre cowriting")
        context = {"data": y}
        return render(request, "ideamall/cowriter.html", context)
    return render(request, "ideamall/cowriter.html")


@lru_cache(maxsize=None)
def oppor(request):
    x = (
        Commissioning.objects.filter(~Q(user_id=request.user))
        .exclude(com_payment_done=False)
        .order_by("-dateofcommissioning")
    )
    y = (
        Commissioning.objects.filter(~Q(user_id=request.user))
        .exclude(com_payment_done=False)
        .order_by("-comm_credibility")
    )
    for i in x:
        if i.shortlisted.filter(id=request.user.id).exists():
            print(request.user.id, ": shortlist1")
            i.shortlisted_by_me = True
        else:
            i.shortlisted_by_me = False
        i.save()
    global per_page
    paginate_by = request.GET.get("entries", per_page)
    per_page = paginate_by
    paginator = Paginator(x, per_page)
    page = request.GET.get("page")

    try:
        paginated = paginator.get_page(page)
    except PageNotAnInteger:
        paginated = paginator.get_page(1)
    except EmptyPage:
        paginated = paginator.page(paginator.num_pages)
    context = {"data": x, "page_obj": paginated,
               "paginate_by": paginate_by, "credibility": y}
    return render(request, "ideamall/opportunities.html", context)


def makeur(request, commission_id=0):
    try:
        x = Commissioning.objects.get(commission_id=commission_id)
    except:
        return redirect("oppor")

    with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
        body = f.read()

    context_email = {
        "Date": date.today(),
        "Name": x.user_id.email,
        "emailcode": "IM43",
        "heading1": "SPLENDID!",
        "heading2": str(x.projectname) + " has evoked interest!! ",
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context\
    sendemailim(
        x.user_id.email,
        "Someone evoked interest!",
        date.today(),
        context_email,
    )
    if x.viewers.filter(id=request.user.id).exists():
        print("viewers exists")
        x.save()
    else:
        print("viewers not exists")
        x.viewers.add(request.user.id)
        x.save()
    # if x.viewers.all():
    #     user_count = 0
    #     for i in x.viewers.all():
    #         if i.user_id == request.user:
    #             user_count = 1
    #             break
    #     if user_count == 0:
    #         x.viewers.add(request.user)
    #         x.save()
    # else:
    #     x.viewers.add(request.user)
    #     x.save()

    if x.maker.all():
        for i in x.maker.all():
            if i.user_id == request.user:
                y = i
                context = {"data": x, "maker": y}
                break
            else:
                z = {
                    "read_script_available": "",
                    "auction_project_based": "",
                    "deleiver_script": "",
                    "accept_assignments": "",
                }
                context = {"data": x, "maker": z}

    else:
        z = {
            "read_script_available": "",
            "auction_project_based": "",
            "deleiver_script": "",
            "accept_assignments": "",
        }
        context = {"data": x, "maker": z}

    if request.method == "POST":
        y = Make()
        y.user_id = request.user
        y.highestpayment = request.POST.get("highest")
        y.highestpayment_amount = request.POST.get("amount")

        if y.highestpayment_amount == 0:
            pass
        elif int(y.highestpayment_amount) > 0 and int(y.highestpayment_amount) <= 30:
            y.resp_credibility = 1
        elif int(y.highestpayment_amount) > 30 and int(y.highestpayment_amount) <= 300:
            y.resp_credibility = 2
        elif (
            int(y.highestpayment_amount) > 300 and int(
                y.highestpayment_amount) <= 3000
        ):
            y.resp_credibility = 3
        elif (
            int(y.highestpayment_amount) > 3000
            and int(y.highestpayment_amount) <= 30000
        ):
            y.resp_credibility = 4
        elif (
            int(y.highestpayment_amount) > 30000
            and int(y.highestpayment_amount) <= 300000
        ):
            y.resp_credibility = 5
        else:
            y.resp_credibility = 6

        y.scriptpage_paid = request.POST.get("paid")

        temp = int(y.scriptpage_paid) / 10
        y.resp_credibility += int(temp)

        y.script_filmed = request.POST.get("filmed")

        temp = int(y.script_filmed) / 10
        y.resp_credibility += int(temp)

        y.script_production_phase = request.POST.get("phase")

        temp = int(y.script_production_phase) / 50
        y.resp_credibility += int(temp)

        y.scripted_pages = request.POST.get("pages")

        temp = int(y.scripted_pages) / 100
        y.resp_credibility += int(temp)
        y.any_other = request.POST.get("other")
        y.lang_known = request.POST.get("primarylang")
        y.scripts_known = request.POST.getlist("knownscripts[]")
        y.date_of_first_quote = date.today()
        y.offer = "first_quote"

        if request.POST.get("available"):
            y.read_script_available = True
            y.language = request.POST.get("language")
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM46",
                "heading1": "REVEALED!",
                "heading2": "An screenplay similar to "
                + str(x.projectname)
                + " is already written!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Someone Revealed project " + str(x.projectname),
                date.today(),
                context_email,
            )

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM47",
                "heading1": "BUCK UP!",
                "heading2": str(request.user.email)
                + " has been offered for "
                + str(x.projectname)
                + " !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Someone offered project for " + str(x.projectname),
                date.today(),
                context_email,
            )
        if request.POST.get("based"):
            y.auction_project_based = True
            y.url = request.POST.get("url")
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM48",
                "heading1": "SURPRISE!",
                "heading2": "A project similar to"
                + str(x.projectname)
                + "is under the hammer !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Someone  refers the commissioner to an auction of Script on similar idea for "
                + str(x.projectname),
                date.today(),
                context_email,
            )

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM49",
                "heading1": "INTERESTING!",
                "heading2": "Someone wants an script similar to "
                + str(x.projectname)
                + " written!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Someone want script for " + str(x.projectname),
                date.today(),
                context_email,
            )

        if request.POST.get("script"):
            y.deleiver_script = True
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM51",
                "heading1": "SUPERB!",
                "heading2": "Someone is ready to write " + str(x.projectname) + " !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Someone is ready to write " + str(x.projectname),
                date.today(),
                context_email,
            )

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM50",
                "heading1": "STAKED!",
                "heading2": "Your interest in writing "
                + str(x.projectname)
                + " is conveyed!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Your acceptance conveyed for " + str(x.projectname),
                date.today(),
                context_email,
            )

        if request.POST.get("assignments"):
            y.date_of_first_quote = date.today()
            y.offer = "first_quote"
            y.accept_assignments = True
            y.negotiable = request.POST.get("negotiable")
            y.date_of_deleivery = request.POST.get("date")
            y.payment_required = request.POST.get("payment")
            y.payment_amount = request.POST.get("payment_amount")
            y.terms_on_sign = request.POST.get("sign")
            y.terms_on_bound = request.POST.get("bound")
            y.terms_on_scriptlocking = request.POST.get("script_locking")
            y.terms_on_filmrelease = request.POST.get("film")
            y.first_quote_bonus = request.POST.get("bonus")

            if y.negotiable == "No":
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM58",
                    "heading1": "CHECK OUT!",
                    "heading2": "Someone has quoted terms for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "Someone has accepted "
                    + str(x.projectname)
                    + "without negotiation",
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM59",
                    "heading1": "DAZZLE!",
                    "heading2": "Your quote for writing "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "acceptance of " + str(x.projectname) +
                    " without negotation",
                    date.today(),
                    context_email,
                )
            else:
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM60",
                    "heading1": "CHECK OUT!",
                    "heading2": "Someone has quoted terms for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "Someone has accepted " +
                    str(x.projectname) + "with negotiation",
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM61",
                    "heading1": "DAZZLE!",
                    "heading2": "Your quote for writing "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "acceptance of " + str(x.projectname) + " with negotation",
                    date.today(),
                    context_email,
                )

        y.save()
        x.maker.add(y)
        x.save()
        
        # store data in central database
        cd = centralDatabase.objects.get(user_id=request.user)
        cd.about = y.any_other
        cd.language = y.lang_known
        cd.save()
        
        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": x.user_id.email,
            "emailcode": "IM44",
            "heading1": "WOW!",
            "heading2": str(x.projectname) + " has a response!!",
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context\
        temp_str = "Someone responded on " + str(x.projectname)
        sendemailim(
            x.user_id.email,
            temp_str,
            date.today(),
            context_email,
        )

        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": request.user.email,
            "emailcode": "IM45",
            "heading1": "BUCK UP!",
            "heading2": "Your interest in " + str(x.projectname) + " is conveyed!!",
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context\
        sendemailim(
            request.user.email,
            "Interest Conveyed to Commissioner!",
            date.today(),
            context_email,
        )
        context = {"data": x}

        return redirect("oppor")

    return render(request, "ideamall/make.html", context)


def conversion_redirect(request):
    return render(request, "conversion/conversion.html")


def tabletennis(request):

    if request.method == "POST":

        maker_id = request.POST.get("make_id")
        x = Commissioning.objects.get(maker=maker_id)
        y = Make.objects.get(uid=maker_id)
        print(x.user_id.email, ":x_user")
        print(y.user_id.email, ":y_user")
        print(request.user.email, ":request_user")
        if request.POST.get("offer") == "accept":
            # send mail

            if y.offer == "first_quote":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM64",
                    "heading1": "STAKED!",
                    "heading2": "Your decision for assigning "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "acceptance for offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                # mail to responder
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM65",
                    "heading1": "SUPERB!",
                    "heading2": "The Assignment Commissioner has accepted your quote for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "someone accepted offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )
                print("first_quote_two")
            elif y.offer == "first_revision":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()
                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM74",
                    "heading1": "SUPERB!",
                    "heading2": "Someone has accepted your offer for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "Someone accepted to write " + str(x.projectname),
                    date.today(),
                    context_email,
                )
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()
                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM75",
                    "heading1": "STAKED!",
                    "heading2": "Your acceptance of writing "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "acceptance conveyed for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

            elif y.offer == "second_quote":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM90",
                    "heading1": "STAKED!",
                    "heading2": "Your decision for assigning "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "acceptance for offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                # mail to responder
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM91",
                    "heading1": "SUPERB!",
                    "heading2": "The Assignment Commissioner has accepted your quote for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "someone accepted offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

            elif y.offer == "second_revision":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()
                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM96",
                    "heading1": "SUPERB!",
                    "heading2": "Someone has accepted offer for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "Someone accepted to write " + str(x.projectname),
                    date.today(),
                    context_email,
                )
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()
                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM97",
                    "heading1": "STAKED!",
                    "heading2": "Your acceptance of writing "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "acceptance conveyed for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

            y.offer = "accept"
            y.date_accept = date.today()
            y.save()
        elif request.POST.get("offer") == "decline":
            # send mail
            if y.offer == "first_quote":
                print("rejection mail started")
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM62",
                    "heading1": "HALTED!",
                    "heading2": "Your rejection of quote for "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Rejection for offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )
                print("rejection mail send1")
                # mail to responder
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM63",
                    "heading1": "AMEND YOUR TERMS!",
                    "heading2": "for writing " + str(x.projectname) + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "someone Rejected for offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )
                print("rejection mail send2")
            elif y.offer == "first_revision":
                # send mail

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM76",
                    "heading1": "AMEND YOUR TERMS!",
                    "heading2": "for writing " + str(x.projectname) + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "Someone rejected to write " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM77",
                    "heading1": "HALTED!",
                    "heading2": "Your rejection of quote for "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "rejection conveyed for " + str(x.projectname),
                    date.today(),
                    context_email,
                )
            elif y.offer == "second_quote":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM88",
                    "heading1": "HALTED!",
                    "heading2": "Your rejection of second quote for "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Rejection for offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                # mail to responder
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM63",
                    "heading1": "AMEND YOUR TERMS!",
                    "heading2": "for writing " + str(x.projectname) + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "someone Rejected for offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )

            elif y.offer == "second_revision":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM98",
                    "heading1": "CLOSED!",
                    "heading2": " An opportunity to assign "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "Someone rejected to write " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM99",
                    "heading1": "RELINQUISHED!",
                    "heading2": "Your interest in writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "rejection conveyed for " + str(x.projectname),
                    date.today(),
                    context_email,
                )
            y.offer = "reject"
            y.date_reject = date.today()
            y.save()

        elif request.POST.get("offer") == "auction":
            # send mail
            y.offer = "auction"
            y.date_auction = date.today()
            y.save()
        elif request.POST.get("offer") == "hold":
            # send mail
            if y.offer == "first_quote":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM66",
                    "heading1": "ADJOURNED!",
                    "heading2": "You have kept on hold the quote for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "You hold offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                # mail to responder
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM67",
                    "heading1": "SUSPENDED!",
                    "heading2": "Your quote for "
                    + str(x.projectname)
                    + " is placed on shelf!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "Someone hold offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )
            elif y.offer == "first_revision":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM78",
                    "heading1": "SUSPENDED!",
                    "heading2": "Your revised/fresh offer for "
                    + str(x.projectname)
                    + " is placed on shelf!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Someone hold " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM79",
                    "heading1": "ADJOURNED!",
                    "heading2": "You have kept on hold the revised/fresh offer for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "Hold conveyed for " + str(x.projectname),
                    date.today(),
                    context_email,
                )
            elif y.offer == "second_quote":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM92",
                    "heading1": "ADJOURNED!",
                    "heading2": "You have kept on hold the second quote for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "You hold offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                # mail to responder
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM93",
                    "heading1": "SUSPENDED!",
                    "heading2": "Your quote for "
                    + str(x.projectname)
                    + " is placed on shelf!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "Someone hold offer " + str(x.projectname),
                    date.today(),
                    context_email,
                )
            elif y.offer == "second_revision":
                # send mail
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM 100",
                    "heading1": "SUSPENDED!",
                    "heading2": "Your last offer for "
                    + str(x.projectname)
                    + " is placed on shelf!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Someone hold " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM101",
                    "heading1": "ADJOURNED!",
                    "heading2": "You have kept on hold the last offer for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "Hold conveyed for " + str(x.projectname),
                    date.today(),
                    context_email,
                )
            else:
                pass
            y.offer = "hold"
            y.date_hold = date.today()
            y.save()

        elif request.POST.get("offer") == "ask_script":
            # send mail (User is asking for the script, please communicate with the commissioner and contact details)
            y.offer = "ask_script"
            y.date_ask = date.today()
            y.save()
        elif request.POST.get("offer") == "fresh_accept":

            y.offer = "fresh_accept"
            y.date_fresh_accept = date.today()
            y.save()

        elif request.POST.get("offer") == "fresh_reject":

            y.offer = "fresh_reject"
            y.date_fresh_reject = date.today()
            y.save()

        elif request.POST.get("offer") == "freshoffer_after_hold":
            y.offer = "first_revision"
            y.revised_offer_date = date.today()
            y.revised_offer_deliverydate = request.POST.get("deliverydate")
            y.revised_payment = request.POST.get("payment")
            y.revised_on_sign = request.POST.get("onsign")
            y.revised_on_bound = request.POST.get("onbound")
            y.revised_scriptlocking = request.POST.get("scriptlocking")
            y.revised_filmrelease = request.POST.get("filmrelease")
            if request.POST.get("bonus"):
                y.revised_bonus = request.POST.get("bonus")
            else:
                y.revised_bonus = "0"

            y.save()
        elif request.POST.get("offer") == "accepted":
            y.offer = "first_revision"
            y.revised_offer_date = date.today()
            y.revised_offer_deliverydate = request.POST.get("deliverydate")
            y.revised_payment = request.POST.get("payment")
            y.revised_on_sign = request.POST.get("onsign")
            y.revised_on_bound = request.POST.get("onbound")
            y.revised_scriptlocking = request.POST.get("scriptlocking")
            y.revised_filmrelease = request.POST.get("filmrelease")
            if request.POST.get("bonus"):
                y.revised_bonus = request.POST.get("bonus")
            else:
                y.revised_bonus = "0"
            y.save()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM70",
                "heading1": "RENEWED!",
                "heading2": "Your fresh offer for writing "
                + str(x.projectname)
                + " is delivered!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Your fresh ffer for " + str(x.projectname),
                date.today(),
                context_email,
            )

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": y.user_id.email,
                "emailcode": "IM72",
                "heading1": "CHECK OUT!",
                "heading2": str(x.projectname)
                + " Commissioner has made a fresh offer!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                y.user_id.email,
                "Someone gives fresh offer for " + str(x.projectname),
                date.today(),
                context_email,
            )
        else:
            if y.offer == "first_quote":
                y.offer = "first_revision"
                y.revised_offer_date = date.today()
                y.revised_offer_deliverydate = request.POST.get("deliverydate")
                y.revised_payment = request.POST.get("payment")
                y.revised_on_sign = request.POST.get("onsign")
                y.revised_on_bound = request.POST.get("onbound")
                y.revised_scriptlocking = request.POST.get("scriptlocking")
                y.revised_filmrelease = request.POST.get("filmrelease")
                if request.POST.get("bonus"):
                    y.revised_bonus = request.POST.get("bonus")
                else:
                    y.revised_bonus = "0"
                y.save()
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM68",
                    "heading1": "ASSERTED!",
                    "heading2": "Your revised offer for writing "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Your revised the offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM69",
                    "heading1": "CHECK OUT!",
                    "heading2": "The Assignment Commissioner  has revised terms for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "Someone revised offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

            elif y.offer == "first_revision":
                y.offer = "second_quote"
                y.second_quote_date = date.today()
                y.second_quote_deliverydate = request.POST.get("deliverydate")
                y.second_quote_payment = request.POST.get("payment")
                y.second_quote_on_sign = request.POST.get("onsign")
                y.second_quote_on_bound = request.POST.get("onbound")
                y.second_quote_scriptlocking = request.POST.get(
                    "scriptlocking")
                y.second_quote_filmrelease = request.POST.get("filmrelease")
                if request.POST.get("bonus"):
                    y.second_quote_bonus = request.POST.get("bonus")
                else:
                    y.second_quote_bonus = "0"
                y.save()
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": x.user_id.email,
                    "emailcode": "IM84",
                    "heading1": "CHECK OUT!",
                    "heading2": "Someone has made a fresh offer for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    x.user_id.email,
                    "someone revised the offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM86",
                    "heading1": "RENEWED!",
                    "heading2": "Your fresh offer for writing "
                    + str(x.projectname)
                    + " is delivered!! ",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Offer revised for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

            elif y.offer == "second_quote":
                y.offer = "final_revision"
                y.final_date = date.today()
                y.final_deliverydate = request.POST.get("deliverydate")
                y.final_payment = request.POST.get("payment")
                y.final_on_sign = request.POST.get("onsign")
                y.final_on_bound = request.POST.get("onbound")
                y.final_scriptlocking = request.POST.get("scriptlocking")
                y.final_filmrelease = request.POST.get("filmrelease")
                if request.POST.get("bonus"):
                    y.final_bonus = request.POST.get("bonus")
                else:
                    y.final_bonus = "0"
                y.save()
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": request.user.email,
                    "emailcode": "IM94",
                    "heading1": "ASSERTED!",
                    "heading2": "Your last offer for writing "
                    + str(x.projectname)
                    + " is conveyed!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    request.user.email,
                    "Your final revised offer for " + str(x.projectname),
                    date.today(),
                    context_email,
                )

                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.user_id.email,
                    "emailcode": "IM95",
                    "heading1": "CHECK OUT!",
                    "heading2": "The Assignment Commissioner  has made the last offer for writing "
                    + str(x.projectname)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    y.user_id.email,
                    "Someone send final revised offer for " +
                    str(x.projectname),
                    date.today(),
                    context_email,
                )

            elif y.offer == "final_revision":
                y.offer = "final_quote"
                y.final_quote_date = date.today()
                y.final_quote_deliverydate = request.POST.get("deliverydate")
                y.final_quote_payment = request.POST.get("payment")
                y.final_quote_on_sign = request.POST.get("onsign")
                y.final_quote_on_bound = request.POST.get("onbound")
                y.final_quote_scriptlocking = request.POST.get("scriptlocking")
                y.final_quote_filmrelease = request.POST.get("filmrelease")
                if request.POST.get("bonus"):
                    y.final_quote_bonus = request.POST.get("bonus")
                else:
                    y.final_quote_bonus = "0"
                y.save()
            else:
                pass
            x = Commissioning.objects.get(maker=maker_id)
            context = {"data": x, "maker": x.maker.all(), "lang": "Finnish"}
        return render(request, "ideamall/view.html", context)
    else:
        return render(request, "ideamall/view.html")


def reminder(request):
    if request.method == "POST":
        x = Commissioning.objects.get(commission_id=request.POST.get("comid"))
        if request.user.email != x.user_id.email:
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM72",
                "heading1": "EXPLORE!",
                "heading2": "Someone has requested a review of the offer for writing "
                + str(x.projectname)
                + " !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Someone send reminder for " + str(x.projectname),
                date.today(),
                context_email,
            )

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM73",
                "heading1": "REVIVED!",
                "heading2": " Your request for review of"
                + str(x.projectname)
                + "offer is conveyed!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "reminder for " + str(x.projectname) + "is sent",
                date.today(),
                context_email,
            )
        else:
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM56",
                "heading1": "REVIVED!",
                "heading2": "Your request for review of "
                + str(x.projectname)
                + " offer is conveyed!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Someone set reminder for " + str(x.projectname),
                date.today(),
                context_email,
            )

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM57",
                "heading1": "EXPLORE!",
                "heading2": str(x.projectname)
                + " Commissioner has requested a review of the offer!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "reminder for " + str(x.projectname),
                date.today(),
                context_email,
            )
        return HttpResponse("mail send")


def commission_view(request, commission_id):
    x = Commissioning.objects.get(commission_id=commission_id)

    if x.user_id == request.user:
        count = 0
        for i in x.maker.all():
            count = count + 1
        context = {"data": x, "maker": x.maker.all(), "responder_count": count}
        return render(request, "ideamall/view.html", context)
    else:
        return redirect("commssioningpage")


# Below Auction


def showcase(request):
    if request.method == "POST":
        gmt = time.gmtime()
        ts = calendar.timegm(gmt)
        x = Showcase()
        x.showcase_string = str(time.time()) + "-showcase"
        file_size = 0
        x.user_id = request.user
        x.loglines = request.POST.get("loglines")
        x.projecttitle = request.POST.get("projecttitle")
        x.languagedialogues = request.POST.get("languagedialogues")
        x.languageactionlines = request.POST.get("languageactionlines")
        x.genre = request.POST.get("genre")
        if x.genre == "Other":
            x.genre_other = request.POST.get("showace_genre_other")

        if request.POST.get("subgenre"):
            x.subgenre = request.POST.get("subgenre")

        project_type = ""
        if request.POST.get("shortfilm"):
            x.shortfilm = True
            project_type += "Shortfilm, "
        if request.POST.get("documentory"):
            x.documentory = True
            project_type += "Documentory, "
        if request.POST.get("webseries"):
            x.webseries = True
            project_type += "Web-series, "
        if request.POST.get("tvserial"):
            x.tvserial = True
            project_type += "TV Serial, "
        if request.POST.get("featurefilm"):
            x.featurefilm = True
            project_type += "Feature Film, "
        if request.POST.get("other"):
            x.other = True
            x.other_value = request.POST.get("otheropn")
            project_type += str(request.POST.get("otheropn"))
        x.projecttype = project_type
        x.setintime = request.POST.get("setintime")
        if request.POST.get("setingeography"):
            x.setingeography = request.POST.get("setingeography")
        x.duration = request.POST.get("duration")
        if request.POST.get("copyright") == True:
            x.copyright = True
            x.registered_with = request.POST.get("registered_with")
        else:
            x.copyright = False
        if request.POST.get("anycoauthor") == True:
            x.anycoauthor = True
            x.nameofcoauthor = request.POST.get("nameofcoauthor")
            x.emailidcoauthor = request.POST.get("emailid")
        else:
            x.copyright = False
        x.budgetcurrency = request.POST.get("projectbudget")
        x.budgetamount = request.POST.get("budgetamount")
        x.projectstatus = request.POST.get("projectstatus")
        if request.POST.get("noofscenes1"):
            x.noofscenes = request.POST.get("noofscenes1")
        if request.POST.get("noofcharacters1"):
            x.noofcharacters = request.POST.get("noofcharacters1")
        if request.POST.get("nooflocations1"):
            x.nooflocations = request.POST.get("nooflocations1")
        if request.POST.get("specialrequirement1"):
            x.specialrequirement = request.POST.get("specialrequirement1")
        if request.POST.get("noofscenes"):
            x.noofscenes = request.POST.get("noofscenes")
        if request.POST.get("noofcharacters"):
            x.noofcharacters = request.POST.get("noofcharacters")
        if request.POST.get("nooflocations"):
            x.nooflocations = request.POST.get("nooflocations")
        if request.POST.get("specialrequirement"):
            x.specialrequirement = request.POST.get("specialrequirement")
        if request.POST.get("starcast"):
            x.starcast = request.POST.get("starcast")
        if request.FILES.get("uploadonepager"):
            onepageruploaded = request.FILES.get("uploadonepager")
            file_size += onepageruploaded.size

            onepageruploaded = upload_to_ipfs(
                onepageruploaded, x.projecttitle, "UploadOnePager", request.user.email, ts
            )
            x.onepageruploaded = onepageruploaded

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM3",
                "heading1": "FLASHED!",
                "heading2": f"Your idea is available for the MNF Community!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "One pager uploaded Successfully!",
                date.today(),
                context_email,
            )

            # VIEWING PERMISSION CODE
            x.whocansee_onepager = "noone"
            validation_needed = True

            print(request.POST.get("UnAnyonepager"))
            print(request.POST.get("auctionpager"))
            print(request.POST.get("Anyoneafterpager"))
            print(request.POST.get("Someonewhopager"))
            print(request.POST.get("Someoneinterestedpager"))
            print(request.POST.get("Someonefinancingpager"))
            print(request.POST.get("Someoneaquiringpager"))
            print(request.POST.get("Someonebuyingpager"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("UnAnyonepager") == "UnAnyonepager":
                    print("2*"*10)
                    x.whocansee_onepager = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionpager") == "Auction bidder":
                    print("4*"*10)
                    x.whocansee_onepager = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterpager") == "Auction bidder":
                    print("6*"*10)
                    x.whocansee_onepager = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhopager") == "Auction bidder":
                    print("8*"*10)
                    x.whocansee_onepager = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedpager") == "Interested co-producing":
                    print("10*"*10)
                    x.whocansee_onepager = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingpager") == "Interested in Full":
                    print("12*"*10)
                    x.whocansee_onepager = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringpager") == "Acquiring limited":
                    print("14*"*10)
                    x.whocansee_onepager = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingpager") == "Interested in buying all":
                    print("16*"*10)
                    x.whocansee_onepager = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_onepager, " : First run success part 2")

        if request.FILES.get("uploadstory"):
            storyuploaded = request.FILES.get("uploadstory")
            file_size += storyuploaded.size

            storyuploaded = upload_to_ipfs(
                storyuploaded, x.projecttitle, "storyuploaded", request.user.email, ts
            )
            x.storyuploaded = storyuploaded

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM4",
                "heading1": "EXPANDED!",
                "heading2": str(x.projecttitle) + " story is now on Idea Mall!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Story uploaded Successfully!",
                date.today(),
                context_email,
            )

            # VIEWING PERMISSION CODE
            x.whocansee_story = "noone"
            validation_needed = True

            print(request.POST.get("Anyonestory"))
            print(request.POST.get("auctionstory"))
            print(request.POST.get("Anyoneafterstory"))
            print(request.POST.get("Someonewhostory"))
            print(request.POST.get("Someoneinterestedstory"))
            print(request.POST.get("Someonefinancingstory"))
            print(request.POST.get("Someoneaquiringstory"))
            print(request.POST.get("Someonebuyingstory"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonestory") == "Anyonestoryyy":
                    print("2*"*10)
                    x.whocansee_story = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionstory") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_story = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterstory") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_story = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhostory") == "Who has shortlisted the ideaa":
                    print("8*"*10)
                    x.whocansee_story = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedstory") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_story = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingstory") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_story = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringstory") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_story = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingstory") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_story = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_story, " : First run success")

        if request.POST.get("scriptsample"):
            samplescriptuploaded = request.POST.get("scriptsample")
            samplescriptuploaded = upload_to_ipfs(
                samplescriptuploaded,
                x.projecttitle,
                "samplescriptuploaded",
                request.user.email, ts
            )
            x.samplescriptuploaded = samplescriptuploaded

            # VIEWING PERMISSION CODE
            x.whocansee_samplescript = "noone"
            validation_needed = True

            print(request.POST.get("Anyonescript"))
            print(request.POST.get("auctionscript"))
            print(request.POST.get("Anyoneafterscript"))
            print(request.POST.get("Someonewhoscript"))
            print(request.POST.get("Someoneinterestedscript"))
            print(request.POST.get("Someonefinancingscript"))
            print(request.POST.get("Someoneaquiringscript"))
            print(request.POST.get("Someonebuyingscript"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonescript") == "Anyonescripttt":
                    print("2*"*10)
                    x.whocansee_samplescript = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionscript") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_samplescript = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterscript") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_samplescript = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhoscript") == "Who has shortlisted the ideaa":
                    print("8*"*10)
                    x.whocansee_samplescript = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedscript") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_samplescript = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingscript") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_samplescript = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringscript") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_samplescript = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingscript") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_samplescript = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_samplescript, " : First run success")

        elif request.FILES.get("uploadsamplescript"):

            samplescriptuploaded = request.FILES.get("uploadsamplescript")
            file_size += samplescriptuploaded.size

            samplescriptuploaded = upload_to_ipfs(
                samplescriptuploaded,
                x.projecttitle,
                "samplescriptuploaded",
                request.user.email, ts
            )
            x.samplescriptuploaded = samplescriptuploaded

            # central = MNFScriptDatabase_2()
            # central.script_file = request.FILES.get("uploadsamplescript")
            # central.user_id = request.user
            # central.uploaded_from = "ideamall"
            # central.script_id = "scr_" + str(script_id_generator())
            # central.save()
            # file_size += samplescriptuploaded.size
            try:

                script_upload(request.FILES.get(
                    "uploadsamplescript"), request.user)
            except:
                pass
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM5",
                "heading1": "FLAUNTED!",
                "heading2": "The world can see your script writing skills!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Sample script uploaded Successfully!",
                date.today(),
                context_email,
            )

            # VIEWING PERMISSION CODE
            x.whocansee_samplescript = "noone"
            validation_needed = True

            print(request.POST.get("Anyonescript"))
            print(request.POST.get("auctionscript"))
            print(request.POST.get("Anyoneafterscript"))
            print(request.POST.get("Someonewhoscript"))
            print(request.POST.get("Someoneinterestedscript"))
            print(request.POST.get("Someonefinancingscript"))
            print(request.POST.get("Someoneaquiringscript"))
            print(request.POST.get("Someonebuyingscript"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonescript") == "Anyonescripttt":
                    print("2*"*10)
                    x.whocansee_samplescript = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionscript") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_samplescript = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterscript") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_samplescript = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhoscript") == "Who has shortlisted the ideaa":
                    print("8*"*10)
                    x.whocansee_samplescript = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedscript") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_samplescript = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingscript") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_samplescript = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringscript") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_samplescript = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingscript") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_samplescript = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_samplescript, " : First run success")

        elif request.FILES.get("fullscriptuploaded"):
            fullscriptuploaded = request.FILES.get("fullscriptuploaded")
            file_size += fullscriptuploaded.size
            fullscriptuploaded = upload_to_ipfs(
                fullscriptuploaded,
                x.projecttitle,
                "fullscriptuploaded",
                request.user.email, ts
            )
            x.fullscriptuploaded = fullscriptuploaded

            try:

                script_upload(request.FILES.get(
                    "fullscriptuploaded"), request.user)
            except:
                pass
            # central = MNFScriptDatabase_2()
            # central.script_file = request.FILES.get("fullscriptuploaded")
            # central.user_id = request.user
            # central.uploaded_from = "ideamall"
            # central.script_id = "scr_" + str(script_id_generator())
            # central.save()
            # file_size += fullscriptuploaded.size
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM6",
                "heading1": "HURRAY!",
                "heading2": str(x.projecttitle) + " Screenplay unveiled on Idea Mall!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Full script uploaded Successfully!",
                date.today(),
                context_email,
            )

            # VIEWING PERMISSION CODE
            x.whocansee_fullscript = "noone"
            validation_needed = True

            print(request.POST.get("Anyonefscript"))
            print(request.POST.get("auctionfscript"))
            print(request.POST.get("Anyoneafterfscript"))
            print(request.POST.get("Someonewhofscript"))
            print(request.POST.get("Someoneinterestedfscript"))
            print(request.POST.get("Someonefinancingfscript"))
            print(request.POST.get("Someoneaquiringfscript"))
            print(request.POST.get("Someonebuyingfscript"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonefscript") == "Anyonefscripttt":
                    print("2*"*10)
                    x.whocansee_fullscript = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionfscript") == "auctionfscripttt":
                    print("4*"*10)
                    x.whocansee_fullscript = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterfscript") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_fullscript = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhofscript") == "Who has shortlisted the ideaa":
                    print("8*"*10)
                    x.whocansee_fullscript = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedfscript") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_fullscript = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingfscript") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_fullscript = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringfscript") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_fullscript = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingfscript") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_fullscript = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_fullscript, " : First run success")

        if request.FILES.get("pitchdeck"):
            pitchdeckuploaded = request.FILES.get("pitchdeck")
            file_size += pitchdeckuploaded.size

            pitchdeckuploaded = upload_to_ipfs(
                pitchdeckuploaded,
                x.projecttitle,
                "pitchdeckuploaded",
                request.user.email, ts
            )
            x.pitchdeckuploaded = pitchdeckuploaded

            # s3.Bucket(BUCKET).upload_file(wav_path, wav_file)

            print("Upload successful")

            # VIEWING PERMISSION CODE
            x.whocansee_pitchdeck = "noone"
            validation_needed = True

            print(request.POST.get("AnyonePitcdeck"))
            print(request.POST.get("auctionPitcdeck"))
            print(request.POST.get("AnyoneafterPitcdeck"))
            print(request.POST.get("SomeonewhoPitcdeck"))
            print(request.POST.get("SomeoneinterestedPitcdeck"))
            print(request.POST.get("SomeonefinancingPitcdeck"))
            print(request.POST.get("SomeoneaquiringPitcdeck"))
            print(request.POST.get("SomeonebuyingPitcdeck"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("AnyonePitcdeck") == "AnyonePitcdeckkk":
                    print("2*"*10)
                    x.whocansee_pitchdeck = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionPitcdeck") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_pitchdeck = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("AnyoneafterPitcdeck") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_pitchdeck = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("SomeonewhoPitcdeck") == "Who has shortlisted the ideaa":
                    print("8*"*10)
                    x.whocansee_pitchdeck = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("SomeoneinterestedPitcdeck") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_pitchdeck = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("SomeonefinancingPitcdeck") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_pitchdeck = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("SomeoneaquiringPitcdeck") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_pitchdeck = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("SomeonebuyingPitcdeck") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_pitchdeck = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_pitchdeck, " : First run success")

        if request.FILES.get("samplenarrationuploaded"):
            samplenarrationuploaded = request.FILES.get(
                "samplenarrationuploaded")
            file_size += samplenarrationuploaded.size

            samplenarrationuploaded = upload_to_ipfs(
                samplenarrationuploaded,
                x.projecttitle,
                "samplenarrationuploaded",
                request.user.email, ts
            )
            x.samplenarrationuploaded = samplenarrationuploaded

            # VIEWING PERMISSION CODE
            x.whocansee_samplenarration = "noone"
            validation_needed = True

            print(request.POST.get("Anyonenarration"))
            print(request.POST.get("auctionnarration"))
            print(request.POST.get("Anyoneafternarration"))
            print(request.POST.get("Someonewhonarration"))
            print(request.POST.get("Someoneinterestednarration"))
            print(request.POST.get("Someonefinancingnarration"))
            print(request.POST.get("Someoneaquiringnarration"))
            print(request.POST.get("Someonebuyingnarration"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonenarration") == "Anyonenarrationnn":
                    print("2*"*10)
                    x.whocansee_samplenarration = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionnarration") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_samplenarration = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafternarration") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_samplenarration = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhonarration") == "Who has shortlisted the ideaaa":
                    print("8*"*10)
                    x.whocansee_samplenarration = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestednarration") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_samplenarration = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingnarration") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_samplenarration = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringnarration") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_samplenarration = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingnarration") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_samplenarration = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_samplenarration, " : First run success")

        if request.FILES.get("characterintrouploaded"):
            characterintrouploaded = request.FILES.get(
                "characterintrouploaded")
            file_size += characterintrouploaded.size
            x.characterintrouploaded = upload_to_ipfs(
                characterintrouploaded,
                x.projecttitle,
                "characterintrouploaded",
                request.user.email, ts
            )

            # VIEWING PERMISSION CODE
            x.whocansee_charintroduction = "noone"
            validation_needed = True

            print(request.POST.get("Anyoneintro"))
            print(request.POST.get("auctionintro"))
            print(request.POST.get("Anyoneafterintro"))
            print(request.POST.get("Someonewhointro"))
            print(request.POST.get("Someoneinterestedintro"))
            print(request.POST.get("Someonefinancingintro"))
            print(request.POST.get("Someoneaquiringintro"))
            print(request.POST.get("Someonebuyingintro"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyoneintro") == "Anyoneintrooo":
                    print("2*"*10)
                    x.whocansee_charintroduction = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionintro") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_charintroduction = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterintro") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_charintroduction = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhointro") == "Who has shortlisted the ideaaa":
                    print("8*"*10)
                    x.whocansee_charintroduction = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedintro") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_charintroduction = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingintro") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_charintroduction = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringintro") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_charintroduction = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingintro") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_charintroduction = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_charintroduction, " : First run success")

            # file_size += characterintrouploaded.size
        if request.FILES.get("scriptanalysisuploaded"):
            scriptanalysisuploaded = request.FILES.get(
                "scriptanalysisuploaded")
            file_size += scriptanalysisuploaded.size

            scriptanalysisuploaded = upload_to_ipfs(
                scriptanalysisuploaded,
                x.projecttitle,
                "scriptanalysisuploaded",
                request.user.email, ts
            )
            x.scriptanalysisuploaded = scriptanalysisuploaded

            # VIEWING PERMISSION CODE
            x.whocansee_scriptanalysis = "noone"
            validation_needed = True

            print(request.POST.get("Anyonedetail"))
            print(request.POST.get("auctiondetails"))
            print(request.POST.get("Anyoneafterdetails"))
            print(request.POST.get("Someonewhodetails"))
            print(request.POST.get("Someoneinteresteddetails"))
            print(request.POST.get("Someonefinancingdetails"))
            print(request.POST.get("Someoneaquiringdetails"))
            print(request.POST.get("Someonebuyingdetails"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonedetail") == "Anyonedetailll":
                    print("2*"*10)
                    x.whocansee_scriptanalysis = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctiondetails") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_scriptanalysis = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterdetails") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_scriptanalysis = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhodetails") == "Who has shortlisted the ideaaa":
                    print("8*"*10)
                    x.whocansee_scriptanalysis = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinteresteddetails") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_scriptanalysis = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingdetails") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_scriptanalysis = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringdetails") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_scriptanalysis = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingdetails") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_scriptanalysis = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_scriptanalysis, " : First run success")

        # To do PR request changes Date at - 03 Oct
        if request.FILES.get("narratefulluploaded"):
            narratefulluploaded = request.FILES.get("narratefulluploaded")
            file_size += narratefulluploaded.size

            narratefulluploaded = upload_to_ipfs(
                narratefulluploaded,
                x.projecttitle,
                "narratefulluploaded",
                request.user.email, ts
            )
            x.narratefulluploaded = narratefulluploaded

            print(x.narratefulluploaded, " : Path found 14")

            # VIEWING PERMISSION CODE
            x.whocansee_fullnarration = "noone"
            validation_needed = True

            print(request.POST.get("Anyonefnarration"))
            print(request.POST.get("auctionfnarration"))
            print(request.POST.get("Anyoneafterfnarration"))
            print(request.POST.get("Someonewhofnarration"))
            print(request.POST.get("Someoneinterestedfnarration"))
            print(request.POST.get("Someonefinancingfnarration"))
            print(request.POST.get("Someoneaquiringfnarration"))
            print(request.POST.get("Someonebuyingfnarration"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonefnarration") == "Anyonefnarrationnn":
                    print("2*"*10)
                    x.whocansee_fullnarration = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionfnarration") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_fullnarration = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterfnarration") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_fullnarration = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhofnarration") == "Who has shortlisted the ideaaa":
                    print("8*"*10)
                    x.whocansee_fullnarration = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedfnarration") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_fullnarration = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingfnarration") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_fullnarration = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringfnarration") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_fullnarration = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingfnarration") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_fullnarration = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_fullnarration, " : First run success")

        if request.FILES.get("samplefootageuploaded"):
            samplefootageuploaded = request.FILES.get("samplefootageuploaded")
            file_size += samplefootageuploaded.size
            samplefootageuploaded = upload_to_ipfs(
                samplefootageuploaded,
                x.projecttitle,
                "samplefootageuploaded",
                request.user.email, ts
            )
            x.samplefootageuploaded = samplefootageuploaded

            # file_size += samplefootageuploaded.size
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM7",
                "heading1": "EXHIBITED!",
                "heading2": str(x.projecttitle) + " Scene is on display!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Sample footage uploaded Successfully!",
                date.today(),
                context_email,
            )

            # VIEWING PERMISSION CODE
            x.whocansee_samplefootage = "noone"
            validation_needed = True

            print(request.POST.get("Anyonefootage"))
            print(request.POST.get("auctionfootage"))
            print(request.POST.get("Anyoneafterfootage"))
            print(request.POST.get("Someonewhofootage"))
            print(request.POST.get("Someoneinterestedfootage"))
            print(request.POST.get("Someonefinancingfootage"))
            print(request.POST.get("Someoneaquiringfootage"))
            print(request.POST.get("Someonebuyingfootage"))

            if validation_needed:
                print("1*"*10)
                if request.POST.get("Anyonefootage") == "Anyonefootageee":
                    print("2*"*10)
                    x.whocansee_samplefootage = "anyone"
                    validation_needed = False

            if validation_needed:
                print("3*"*10)
                if request.POST.get("auctionfootage") == "Any auction bidderrr":
                    print("4*"*10)
                    x.whocansee_samplefootage = "any_auction_bidder"
                    validation_needed = False

            if validation_needed:
                print("5*"*10)
                if request.POST.get("Anyoneafterfootage") == "Anyone after signing NDAAA":
                    print("6*"*10)
                    x.whocansee_samplefootage = "signing_nda"
                    validation_needed = False

            if validation_needed:
                print("7*"*10)
                if request.POST.get("Someonewhofootage") == "Who has shortlisted the ideaaa":
                    print("8*"*10)
                    x.whocansee_samplefootage = "shortlisted_idea"
                    validation_needed = False

            if validation_needed:
                print("9*"*10)
                if request.POST.get("Someoneinterestedfootage") == "Interested in co-producinggg":
                    print("10*"*10)
                    x.whocansee_samplefootage = "interested_in_coproducing"
                    validation_needed = False

            if validation_needed:
                print("11*"*10)
                if request.POST.get("Someonefinancingfootage") == "Interested in Full-financinggg":
                    print("12*"*10)
                    x.whocansee_samplefootage = "interested_in_fullfinancing"
                    validation_needed = False

            if validation_needed:
                print("13*"*10)
                if request.POST.get("Someoneaquiringfootage") == "Acquiring limited rightsss":
                    print("14*"*10)
                    x.whocansee_samplefootage = "acquiring_limitedrights"
                    validation_needed = False

            if validation_needed:
                print("15*"*10)
                if request.POST.get("Someonebuyingfootage") == "Interested in buying all righttt":
                    print("16*"*10)
                    x.whocansee_samplefootage = "buying_all_rights"
                    validation_needed = False

            validation_needed = False
            print(x.whocansee_samplefootage, " : First run success")

        # Some how save "who can see what" before purpose
        x.total_file_size = file_size
        x.uploaded_at = ts
        
        # store data in centralDatabase
        cd = centralDatabase.objects.get(user_id=request.user)
        cd.logline = x.loglines
        cd.project_title = x.projecttitle
        cd.language = x.languagedialogues
        cd.language_of_screenplay = x.languageactionlines
        cd.genre = x.genre
        cd.subgenre = x.subgenre
        cd.project_type = x.projecttype
        cd.set_in_time = x.setintime
        cd.set_in_geography = x.setingeography
        cd.project_duration = x.duration
        cd.budget_currency = x.budgetcurrency
        cd.budget_amount = x.budgetamount
        cd.project_status = x.projectstatus
        cd.save()

        if request.POST.get("findcowriter"):
            x.findcowriter = True
            x.save()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM16",
                "heading1": "YOU'LL DO GREAT!",
                "heading2": "Your desire to find a co-writer is widely circulated!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "showcased for co writter",
                date.today(),
                context_email,
            )
            data = Make.objects.filter(lang_known=x.languagedialogues).exclude(
                user_id=request.user
            )
            for i in data:
                print(i.user_id.email, "loopmakeid")
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": i.user_id.email,
                    "emailcode": "IM17",
                    "heading1": "JOIN HANDS!",
                    "heading2": "Someone wants a co-writer in "
                    + str(x.languagedialogues)
                    + " !!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemailim(
                    i.user_id.email,
                    "You may fit for this",
                    date.today(),
                    context_email,
                )
            return redirect("detailpage", x.showcase_id)
        if request.POST.get("commissionproject"):
            x.commissionproject = True
            x.save()
            context = {"data": x}
            return render(request, "ideamall/auctionTocommission.html", context)
        if request.POST.get("partfinancing"):
            x.partfinancing = True
            x.fundrequiredcurrency = request.POST.get("fund_required_currency")
            x.fundrequiredamount = request.POST.get("fund_required_amount")
        if request.POST.get("fullfinancing"):
            x.fullfinancing = True
            x.fundrequiredcurrency = request.POST.get("fund_required_currency")
            x.fundrequiredamount = request.POST.get("fund_required_amount")
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM22",
                "heading1": "CONSORT!",
                "heading2": "Your need of a "
                + str(x.projecttitle)
                + " project partner is set out!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "showcased for full financing",
                date.today(),
                context_email,
            )

        if request.POST.get("auction_fullrights"):
            x.auction_fullrights = True
            x.auctionstartdate = request.POST.get("auctionstartdate")
            x.auctionstopdate = request.POST.get("auctionstopdate")
            x.reservepricecurrency = request.POST.get("reservepricecurrency")
            x.reservepriceamount = request.POST.get("reservepriceamount")

            final_amount = payment(
                x.reservepricecurrency,
                x.projectstatus,
                x.reservepriceamount,
                x.auctionstartdate,
                x.auctionstopdate,
                file_size,
            )
            print(final_amount, "Auction amount latest")
            x.save()
            y = Auction()
            y.auction_string = str(time.time()) + "-auction"
            y.auction_details = x
            y.auction_user = request.user
            y.auction_start_date = request.POST.get("auctionstartdate")
            y.auction_end_date = request.POST.get("auctionstopdate")
            y.currency = request.POST.get("reservepricecurrency")
            y.reserve_price = request.POST.get("reservepriceamount")
            y.next_possible_bid = float(
                int(y.reserve_price) + int(y.reserve_price) * 0.05
            )

            y.save()
            context = {
                "project_title": x.projecttitle,
                "lang_dial": x.languagedialogues,
                "genre": x.genre,
                "project_type": x.projecttype,
                "duration": x.duration,
                "project_status": x.projectstatus,
                "total_amount": final_amount,
            }
            request.session["total_amount"] = final_amount
            request.session["showcase_string"] = x.showcase_string
            request.session["auction_string"] = y.auction_string
            print(
                "xy objects created successfully",
            )
            return render(request, "ideamall/auction_checkout.html", context)

            # Payment Function called
        if request.POST.get("auction_limitedrights"):
            listwithallauctions = []
            x.auction_limitedrights = True
            x.save()
            if request.POST.get("exhibition_duration"):
                if request.POST.get("airlines"):
                    y = Auction()
                    y.auction_user = request.user
                    y.auction_details = x
                    y.is_exhibition = True
                    y.duration_exhibition = request.POST.get(
                        "exhibition_duration")
                    y.non_exclusive = True
                    y.airlines = True
                    if request.POST.get("subtitle_rights"):
                        y.subtitle_rights = True

                    if request.POST.get("dubbing_rights"):
                        y.dubbing_rights = True

                    y.save()
                    listwithallauctions.append(y)

                if request.POST.get("airlines1"):
                    y = Auction()
                    y.auction_user = request.user
                    y.auction_details = x
                    y.is_exhibition = True
                    y.duration_exhibition = request.POST.get(
                        "exhibition_duration")
                    y.non_exclusive = True
                    y.paid_movie_shows = True
                    if request.POST.get("subtitle_rights"):
                        y.subtitle_rights = True

                    if request.POST.get("dubbing_rights"):
                        y.dubbing_rights = True

                    y.save()
                    listwithallauctions.append(y)

                if request.POST.get("airlines2"):
                    y = Auction()
                    y.auction_user = request.user
                    y.auction_details = x
                    y.is_exhibition = True
                    y.duration_exhibition = request.POST.get(
                        "exhibition_duration")
                    y.non_exclusive = True
                    y.private_open_air = True
                    if request.POST.get("subtitle_rights"):
                        y.subtitle_rights = True

                    if request.POST.get("dubbing_rights"):
                        y.dubbing_rights = True

                    y.save()
                    listwithallauctions.append(y)

                broadcast = request.POST.getlist("broadcast[]")
                paired = {}
                # if airline
                for broad in broadcast:
                    finallist = []
                    if broad == "Theatre":
                        cname = []
                        continent = request.POST.getlist("continent[]")
                        countries = request.POST.getlist("countrynew[]")
                        # get_name = country_name['af']
                        if len(countries) == 0:
                            finallist.extend(continent)
                        else:
                            regions = []
                            for country in countries:
                                cname.append(country_name[country])
                                region = request.POST.getlist(country)
                                regions.extend(region)
                            if len(regions) == 0:
                                finallist.extend(cname)
                            else:
                                finallist.extend(regions)
                        paired[broad] = finallist
                    elif broad == "Digital (OTT)":
                        continent = request.POST.getlist("continent1[]")
                        countries = request.POST.getlist("countrynew1[]")
                        if len(countries) == 0:
                            finallist.extend(continent)
                        else:
                            cname = []
                            regions = []
                            for country in countries:
                                cname.append(country_name[country])
                                region = request.POST.getlist(country)
                                regions.extend(region)
                            if len(regions) == 0:
                                finallist.extend(cname)
                            else:
                                finallist.extend(regions)
                        paired[broad] = finallist
                    elif broad == "Sattelite (T.V)":
                        continent = request.POST.getlist("continent2[]")
                        countries = request.POST.getlist("countrynew2[]")
                        if len(countries) == 0:
                            finallist.extend(continent)
                        else:
                            cname = []
                            regions = []
                            for country in countries:
                                cname.append(country_name[country])
                                region = request.POST.getlist(country)
                                regions.extend(region)
                            if len(regions) == 0:
                                finallist.extend(cname)
                            else:
                                finallist.extend(regions)
                        paired[broad] = finallist
                    else:
                        continent = request.POST.getlist("continent3[]")
                        countries = request.POST.getlist("countrynew3[]")
                        if len(countries) == 0:
                            finallist.extend(continent)
                        else:
                            cname = []
                            regions = []
                            for country in countries:
                                cname.append(country_name[country])
                                region = request.POST.getlist(country)
                                regions.extend(region)
                            if len(regions) == 0:
                                finallist.extend(cname)
                            else:
                                finallist.extend(regions)
                        paired[broad] = finallist

                # iterate over paired dictionary and create different auction objects and save basic and specific details
                for keys in paired:
                    for i in paired[keys]:
                        y = Auction()
                        y.auction_user = request.user
                        y.auction_details = x
                        y.platform = keys
                        y.region = i
                        y.is_exhibition = True
                        y.duration_exhibition = request.POST.get(
                            "exhibition_duration")
                        if request.POST.get("NonExclusivelimited"):
                            y.non_exclusive = True

                        else:
                            y.exclusive = True
                        if request.POST.get("subtitle_rights"):
                            y.subtitle_rights = True

                        if request.POST.get("dubbing_rights"):
                            y.dubbing_rights = True

                        y.save()
                        listwithallauctions.append(y)

            if request.POST.get("derivative_duration"):
                rights = request.POST.getlist("derivativerights[]")
                derivatives = {}
                for lists in rights:
                    if lists == "Right to Remake":
                        languages = request.POST.getlist("remake[]")
                        derivatives[lists] = languages
                    elif lists == "Right to make Prequel (s)":

                        languages = request.POST.getlist("Prequel[]")
                        derivatives[lists] = languages

                    elif lists == "Right to make Sequel (s)":

                        languages = request.POST.getlist("Sequel[]")
                        derivatives[lists] = languages

                    elif lists == "Right to make Spin Off (s)":

                        languages = request.POST.getlist("Spin Off[]")
                        derivatives[lists] = languages

                    elif lists == "Right to make Related Web Series":

                        languages = request.POST.getlist("Web[]")
                        derivatives[lists] = languages

                    elif lists == "Right to make Animated Movie(s)":

                        languages = request.POST.getlist("Movie[]")
                        derivatives[lists] = languages

                    else:
                        languages = request.POST.getlist("Short[]")
                        derivatives[lists] = languages
                    print(derivatives, "dictionary of derivatives")
                for j in derivatives:
                    for i in derivatives[j]:
                        # print(keys, i, "all possible aucions")
                        y = Auction()
                        y.auction_user = request.user
                        y.auction_details = x
                        y.language_derivative = i
                        y.is_derivative = True
                        y.duration_derivative = request.POST.get(
                            "derivative_duration")
                        if j == "Right to Remake":
                            y.remake = True

                        elif j == "Right to make Prequel (s)":
                            y.preuel = True

                        elif j == "Right to make Sequel (s)":
                            y.sequel = True

                        elif j == "Right to make Spin Off (s)":
                            y.spin_off = True

                        elif j == "Right to make Related Web Series":
                            y.related_web_series = True

                        elif j == "Right to make Animated Movie(s)":
                            y.animated_movies = True

                        else:
                            y.short_films = True

                        y.save()
                        listwithallauctions.append(y)

            if request.POST.get("music_duration"):
                component = request.POST.getlist("musiccomp[]")
                for i in component:
                    if i == "Musical Composition":
                        platform = request.POST.getlist("platformComp[]")
                        for j in platform:
                            if j == "on DVD":
                                countries = request.POST.getlist(
                                    "countrynew12[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_dvd[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True

                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "on Casettes":
                                countries = request.POST.getlist(
                                    "countrynew22[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_cst[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "on CD ROM":
                                countries = request.POST.getlist(
                                    "countrynew32[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_rom[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Download from internet":
                                countries = request.POST.getlist(
                                    "countrynew42[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_down[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Radio":
                                countries = request.POST.getlist(
                                    "countrynew52[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_radio[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Television":
                                countries = request.POST.getlist(
                                    "countrynew62[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_tele[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Internet platform":
                                countries = request.POST.getlist(
                                    "countrynew72[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_comp_plat[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                    if i == "Audio Recording":
                        platform = request.POST.getlist("platformrecord[]")
                        for j in platform:
                            if j == "on DVD":
                                countries = request.POST.getlist(
                                    "countrynew14[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_dvd[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "on Casettes":
                                countries = request.POST.getlist(
                                    "countrynew24[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_cst[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "on CD ROM":
                                countries = request.POST.getlist(
                                    "countrynew34[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_rom[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Download from internet":
                                countries = request.POST.getlist(
                                    "countrynew44[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_down[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Radio":
                                countries = request.POST.getlist(
                                    "countrynew54[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_radio[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Television":
                                countries = request.POST.getlist(
                                    "countrynew64[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_tele[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Internet platform":
                                countries = request.POST.getlist(
                                    "countrynew74[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_rec_plat[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                    if i == "Song Video":
                        platform = request.POST.getlist("platformvideo[]")
                        for j in platform:
                            if j == "on DVD":
                                countries = request.POST.getlist(
                                    "countrynew16[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_vid_dvd[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "on Casettes":
                                countries = request.POST.getlist(
                                    "countrynew26[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_vid_cst[]"
                                    )

                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "on CD ROM":
                                countries = request.POST.getlist(
                                    "countrynew36[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_vid_rom[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Download from internet":
                                countries = request.POST.getlist(
                                    "countrynew46[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_vid_down[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Radio":
                                countries = request.POST.getlist(
                                    "countrynew56[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent11[]")
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Television":
                                countries = request.POST.getlist(
                                    "countrynew66[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_vid_tele[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)
                            if j == "Internet platform":
                                countries = request.POST.getlist(
                                    "countrynew76[]")
                                if countries:
                                    cities = []
                                    for country in countries:
                                        region = request.POST.getlist(country)
                                        cities.extend(region)
                                    if len(cities) == 0:
                                        regions = countries
                                    else:
                                        regions = cities
                                else:
                                    regions = request.POST.getlist(
                                        "continent_vid_plat[]"
                                    )
                                for k in regions:
                                    y = Auction()
                                    y.copies_sell_duration = request.POST.get(
                                        "music_duration"
                                    )
                                    y.auction_user = request.user
                                    y.auction_details = x
                                    y.is_music = True
                                    if request.POST.get("musicompoExc"):
                                        y.music_exclusive = True
                                    else:
                                        y.music_non_exclusive = True
                                    y.copies_sell_components = i
                                    y.copies_sell_platform = j
                                    y.copies_sell_region = country_name[k]
                                    y.save()
                                    listwithallauctions.append(y)

                if request.POST.get("music_airlines"):
                    y = Auction()
                    y.auction_user = request.user
                    y.auction_details = x
                    y.is_music = True
                    y.music_non_exclusive = True
                    y.airlines = True
                    y.save()
                    listwithallauctions.append(y)

            if request.POST.get("music_in_derivatives"):
                y = Auction()
                y.auction_user = request.user
                y.auction_details = x
                y.is_music = True
                y.right_in_derivatives = True
                y.right_in_derivatives_duration = request.POST.get(
                    "music_in_derivatives"
                )
                y.save()
                listwithallauctions.append(y)

            if request.POST.get("Right to use in Another work"):
                y = Auction()
                y.auction_user = request.user
                y.auction_details = x
                y.is_music = True
                if request.POST.get("musicompoExc"):
                    y.music_exclusive = True
                else:
                    y.music_non_exclusive = True
                y.another_commercial = True
                y.save()
                listwithallauctions.append(y)

            if request.POST.get("merchandise_duration"):
                Continent = request.POST.getlist("continentmerchandise[]")
                Countries = request.POST.getlist("countrynewmerchandise[]")
                finalstates = []
                if len(Countries) == 0:
                    finalstates.extend(Continent)
                else:
                    for i in Countries:
                        states = request.POST.getlist(i)
                        finalstates.extend(states)
                        if len(states) == 0:
                            finalstates.append(i)
                for i in finalstates:
                    y = Auction()
                    y.auction_user = request.user
                    y.auction_details = x
                    y.is_produce = True
                    y.is_produce_region = i
                    y.is_produce_duration = request.POST.get(
                        "merchandise_duration")
                    y.save()
                    listwithallauctions.append(y)
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM25",
                "heading1": "COUNT UP!",
                "heading2": str(x.projecttitle) + "  is up for auction!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Auction for limited rights",
                date.today(),
                context_email,
            )
            return redirect("dormant")
        x.save()
        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": request.user.email,
            "emailcode": "IM1",
            "heading1": "IMMORTAL!",
            "heading2": "Your idea is now forever!!",
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context\
        sendemailim(
            request.user.email,
            "Idea showcased Successfully!",
            date.today(),
            context_email,
        )
        return redirect("browse")
    central = MNFScriptDatabase_2.objects.filter(user_id=request.user)
    for i in central:
        print(i.script_file, "central script")
        print(i.script_file.name, "central_script_name")
    context = {
        "key": COUNTRY_KEY,
        "central": central,
    }
    return render(request, "ideamall/showcase.html", context)


def auction_full_failed(request):
    print(request.session["showcase_string"],
          request.session["auction_string"], " : Why god why?")

    temp = Showcase.objects.filter(showcase_string=request.session["showcase_string"]).exists()
    print(temp)

    Showcase.objects.get(
        showcase_string=request.session["showcase_string"]).delete()
    Auction.objects.get(
        auction_string=request.session["auction_string"]).delete()
    return render(request, "payments/failed.html")


def auction_limited_failed(request):
    Auction.objects.get(
        auction_string=request.session["auction_string"]).delete()
    x = Auction.objects.get(
        auction_details=(
            Showcase.objects.get(
                showcase_string=request.session["showcase_string"])
        ).showcase_id
    ).count()
    if x == 0:
        Showcase.objects.get(
            showcase_string=request.session["showcase_string"]
        ).delete()
    return render(request, "payments/failed.html")


def auction_success(request):
    print("Auction Successful!")
    x = Auction.objects.get(auction_string=request.session["auction_string"])
    x.auc_payment_done = True
    x.save()
    print("Auction Payment Field Updated!")

    with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
        body = f.read()

    context_email = {
        "Date": date.today(),
        "Name": request.user.email,
        "emailcode": "IM25",
        "heading1": "COUNT UP!",
        "heading2": str(x.auction_details.projecttitle) + "  is up for auction!!",
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context\
    sendemailim(
        request.user.email,
        "Auction for full rights",
        date.today(),
        context_email,
    )
    data = Commissioning.objects.filter(
        languagedialogues=x.auction_details.languagedialogues,
        languagescreenplay=x.auction_details.languageactionlines,
        genre=x.auction_details.genre,
    ).exclude(com_payment_done=False)
    if data:
        for i in data:
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": i.user_id.email,
                "emailcode": "IM26",
                "heading1": "TAKE YOUR PICK!",
                "heading2": str(x.auction_details.projecttitle) + "   is up for grab!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                i.user_id.email,
                "Found simillar",
                date.today(),
                context_email,
            )
    return redirect("myauction")


# def browse_div(request):
#     if request.method == "POST":
#         broadcast = request.POST.getlist("broadcast[]")
#         paired = {}
#         for broad in broadcast:
#             finallist = []
#             if broad == "Theatre":
#                 continent = request.POST.getlist("continent[]")
#                 countries = request.POST.getlist("countrynew[]")
#                 if countries is None:
#                     finallist.extend(continent)
#                 else:
#                     for country in countries:
#                         regions = request.POST.getlist(country)
#                         if regions is None:
#                             finallist.extend(country)
#                         else:
#                             finallist.extend(regions)
#                 paired[broad] = finallist
#             elif broad == "Digital (OTT)":
#                 continent = request.POST.getlist("continent1[]")
#                 countries = request.POST.getlist("countrynew1[]")
#                 if countries is None:
#                     finallist.extend(continent)
#                 else:
#                     for country in countries:
#                         regions = request.POST.getlist(country)
#                         if regions is None:
#                             finallist.extend(country)
#                         else:
#                             finallist.extend(regions)
#                 paired[broad] = finallist
#             elif broad == "Sattelite (T.V)":
#                 continent = request.POST.getlist("continent2[]")
#                 countries = request.POST.getlist("countrynew2[]")
#                 if countries is None:
#                     finallist.extend(continent)
#                 else:
#                     for country in countries:
#                         regions = request.POST.getlist(country)
#                         if regions is None:
#                             finallist.extend(country)
#                         else:
#                             finallist.extend(regions)
#                 paired[broad] = finallist
#             else:
#                 continent = request.POST.getlist("continent3[]")
#                 countries = request.POST.getlist("countrynew3[]")
#                 if countries is None:
#                     finallist.extend(continent)
#                 else:
#                     for country in countries:
#                         regions = request.POST.getlist(country)
#                         if regions is None:
#                             finallist.extend(country)
#                         else:
#                             finallist.extend(regions)
#                 paired[broad] = finallist
#         print(paired, "akash001")

#     return render(request, "ideamall/browse_divesh.html")


def showcaseedited(request, id):
    if request.method == "POST":
        x = Showcase.objects.get(showcase_id=id)
        x.shortfilm = False
        x.documentory = False
        x.webseries = False
        x.tvserial = False
        x.featurefilm = False
        x.other = False
        x.other_value = ""

        x.user_id = request.user
        x.loglines = request.POST.get("loglines")
        x.projecttitle = request.POST.get("projecttitle")
        x.languagedialogues = request.POST.get("languagedialogues")
        x.languageactionlines = request.POST.get("languageactionlines")
        x.genre = request.POST.get("genre")
        if x.genre == "Other":
            x.genre_other = request.POST.get("showaceedit_genre_other")

        if request.POST.get("subgenre"):
            x.subgenre = request.POST.get("subgenre")
        project_type = ""
        if request.POST.get("shortfilm"):
            x.shortfilm = True
            project_type += "Shortfilm, "
        if request.POST.get("documentory"):
            x.documentory = True
            project_type += "Documentory, "
        if request.POST.get("webseries"):
            x.webseries = True
            project_type += "Web-series, "
        if request.POST.get("tvserial"):
            x.tvserial = True
            project_type += "TV Serial, "
        if request.POST.get("featurefilm"):
            x.featurefilm = True
            project_type += "Feature Film, "
        if request.POST.get("other"):
            x.other = True
            x.other_value = request.POST.get("otheropn")
            project_type += str(request.POST.get("otheropn"))
        x.projecttype = project_type

        x.setintime = request.POST.get("setintime")
        if request.POST.get("setingeography"):
            x.setingeography = request.POST.get("setingeography")
        x.duration = request.POST.get("duration")
        if request.POST.get("copyright") == "Yes":
            x.copyright = True
            x.registered_with = request.POST.get("registered_with")
        else:
            x.copyright = False
            x.registered_with = ""
        if request.POST.get("anycoauthor") == "Yes":
            x.anycoauthor = True
            x.nameofcoauthor = request.POST.get("nameofcoauthor")
            x.emailidcoauthor = request.POST.get("emailid")
        else:
            x.anycoauthor = False
            x.nameofcoauthor = ""
            x.emailidcoauthor = ""

        x.budgetcurrency = request.POST.get("projectbudget")
        x.budgetamount = request.POST.get("budgetamount")
        x.projectstatus = request.POST.get("projectstatus")
        if request.POST.get("noofscenes1"):
            x.noofscenes = request.POST.get("noofscenes1")
        if request.POST.get("noofcharacters1"):
            x.noofcharacters = request.POST.get("noofcharacters1")
        if request.POST.get("nooflocations1"):
            x.nooflocations = request.POST.get("nooflocations1")
        if request.POST.get("specialrequirement1"):
            x.specialrequirement = request.POST.get("specialrequirement1")
        if request.POST.get("noofscenes"):
            x.noofscenes = request.POST.get("noofscenes")
        if request.POST.get("noofcharacters"):
            x.noofcharacters = request.POST.get("noofcharacters")
        if request.POST.get("nooflocations"):
            x.nooflocations = request.POST.get("nooflocations")
        if request.POST.get("specialrequirement"):
            x.specialrequirement = request.POST.get("specialrequirement")
        if request.POST.get("starcast"):
            x.starcast = request.POST.get("starcast")
        if request.FILES.get("uploadonepager"):
            x.onepageruploaded = request.FILES.get("uploadonepager")
        if request.FILES.get("uploadstory"):
            x.storyuploaded = request.FILES.get("uploadstory")
        if request.POST.get("scriptsample"):
            x.samplescriptuploaded = request.POST.get("scriptsample")

        elif request.FILES.get("uploadsamplescript"):

            x.samplescriptuploaded = request.FILES.get("uploadsamplescript")
            central = MNFScriptDatabase_2()
            central.script_file = request.FILES.get("uploadsamplescript")
            central.user_id = request.user
            central.uploaded_from = "ideamall"
            central.script_id = "scr_" + str(script_id_generator())
            central.save()
        if request.POST.get("fullscript"):
            x.fullscriptuploaded = request.POST.get("fullscript")

        elif request.FILES.get("fullscriptuploaded"):
            x.fullscriptuploaded = request.FILES.get("fullscriptuploaded")
            central = MNFScriptDatabase_2()
            central.script_file = request.FILES.get("fullscriptuploaded")
            central.user_id = request.user
            central.uploaded_from = "ideamall"
            central.script_id = "scr_" + str(script_id_generator())
            central.save()
        if request.FILES.get("pitchdeck"):
            x.pitchdeckuploaded = request.FILES.get("pitchdeck")
        if request.FILES.get("samplenarrationuploaded"):
            x.samplenarrationuploaded = request.FILES.get(
                "samplenarrationuploaded")
        if request.FILES.get("characterintrouploaded"):
            x.characterintrouploaded = request.FILES.get(
                "characterintrouploaded")
        if request.FILES.get("scriptanalysisuploaded"):
            x.scriptanalysisuploaded = request.FILES.get(
                "scriptanalysisuploaded")
        if request.FILES.get("narratefulluploaded"):
            x.narratefulluploaded = request.FILES.get("narratefulluploaded")
        if request.FILES.get("samplefootageuploaded"):
            x.samplefootageuploaded = request.FILES.get(
                "samplefootageuploaded")

        # Some how save "who can see what" before purpose

        if request.POST.get("findcowriter"):
            x.findcowriter = True
            x.save()
            data = Make.objects.filter(
                lang_known=request.POST.get("languagedialogues")
            )  # it should not display self in finding co-writer

            context = {
                "data": data,
            }
            return render(request, "ideamall/cowriter.html", context)
        if request.POST.get("commissionproject"):
            x.commissionproject = True
            x.save()
            context = {"data": x}
            return render(request, "ideamall/auctionTocommission.html", context)
        if request.POST.get("partfinancing"):
            x.partfinancing = True
            x.fundrequiredcurrency = request.POST.get("fund_required_currency")
            x.fundrequiredamount = request.POST.get("fund_required_amount")
        if request.POST.get("fullfinancing"):
            x.fullfinancing = True
            x.fundrequiredcurrency = request.POST.get("fund_required_currency")
            x.fundrequiredamount = request.POST.get("fund_required_amount")
        if request.POST.get("auction_fullrights"):
            x.auction_fullrights = True
            # x.auctionstartdate = request.POST.get("auctionstartdate")
            # x.auctionstopdate = request.POST.get("auctionstopdate")
            x.reservepricecurrency = request.POST.get("reservepricecurrency")
            x.reservepriceamount = request.POST.get("reservepriceamount")
            # function is called and attributes are passed. Function returns amount
            # Ask renu maam to implement payment

            x.save()
            y = Auction()
            y.auction_details = x
            y.auction_user = request.user
            # y.auction_start_date = request.POST.get("auctionstartdate")
            # y.auction_end_date = request.POST.get("auctionstopdate")
            y.currency = request.POST.get("reservepricecurrency")
            y.reserve_price = request.POST.get("reservepriceamount")
            y.save()
            return redirect("myauction")
        if request.POST.get("auction_limitedrights"):
            x.auction_limitedrights = True
            x.save()
            y = Auction()
            y.auction_user = request.user
            y.auction_details = x
            y.save()
            return redirect("myauction")

        x.save()
        return redirect("browse")

    context = {"key": COUNTRY_KEY}
    return render(request, "ideamall/showcase.html", context)


def showcaseupdate(request, id):
    x = Showcase.objects.get(showcase_id=id)
    context = {"data": x, "key": COUNTRY_KEY}
    return render(request, "ideamall/showcase.html", context)


def browse(request):
    x = Showcase.objects.all().order_by("-date_of_submission")
    no_one_seen = Showcase.objects.filter(viewercount=0)
    y = []
    for i in x:
        if i.findcowriter == True:
            if i.user_id == request.user:
                y.append(i)
            else:
                continue
        elif i.commissionproject == True:
            continue
        elif i.auction_fullrights == True:
            if i.reservepriceamount == 0:
                continue
            else:
                z = Auction.objects.filter(
                    auction_details=i.showcase_id, auc_payment_done=True
                ).count()
                if z > 0:
                    y.append(i)
                else:
                    continue
        elif i.auction_limitedrights == True:
            # z = Auction.objects.filter(auction_details=i.showcase_id)
            # for obj in z:
            #     if obj.reserve_price == 0:
            #         continue
            #     else:
            #         y.append(obj)
            if i.reservepriceamount == 0:
                continue
            else:
                count_payment = Auction.objects.filter(
                    auction_details=i.showcase_id, auc_payment_done=True
                ).count()
                if count_payment > 0:
                    y.append(i)
                else:
                    continue
        else:
            y.append(i)

    res = [i for n, i in enumerate(y) if i not in y[:n]]
    global showroom_per_page
    paginate_by = request.GET.get("entries", showroom_per_page)
    showroom_per_page = paginate_by
    paginator = Paginator(res, showroom_per_page)
    page = request.GET.get("page")

    try:
        paginated = paginator.get_page(page)
    except PageNotAnInteger:
        paginated = paginator.get_page(1)
    except EmptyPage:
        paginated = paginator.page(paginator.num_pages)
    context = {"data": x, "page_obj": paginated}
    return render(request, "ideamall/browse.html", context)


def limitedrights(request):
    if request.method == "POST":
        print("Got till here")
        x = Auction.objects.get(auction_id=request.POST.get("auction"))
        print("Found the auction object")
        x.auction_start_date = request.POST.get("start_date")
        x.auction_end_date = request.POST.get("end_date")
        x.currency = request.POST.get("currency_myauction")
        x.reserve_price = request.POST.get("amount_myauction")
        x.auction_string = str(time.time()) + "-auction_limited"
        x.next_possible_bid = float(
            int(x.reserve_price) + int(x.reserve_price) * 0.05)
        print(x.auction_details.showcase_id, "Book12")
        # same as auction full rights
        y = Showcase.objects.get(showcase_id=x.auction_details.showcase_id)
        y.reservepriceamount = x.reserve_price
        y.reservepricecurrency = x.currency
        print("showcase found")
        # status, reserveprize, startdate, enddate, filesize
        payment_amount = payment(
            y.reservepricecurrency,
            y.projectstatus,
            x.reserve_price,
            x.auction_start_date,
            x.auction_end_date,
            y.total_file_size,
        )
        print(payment_amount, " : Dormant Payment")
        y.save()
        x.save()

        # Payment function called

        request.session["total_amount"] = payment_amount
        request.session["showcase_string"] = y.showcase_string
        request.session["auction_string"] = x.auction_string
        request.session["projecttitle"] = y.projecttitle
        request.session["languagedialogues"] = y.languagedialogues
        request.session["genre"] = y.genre
        request.session["projecttype"] = y.projecttype
        request.session["duration"] = y.duration
        request.session["projectstatus"] = y.projectstatus
        print(
            "xy objects created successfully",
        )
        context = {
            "project_title": y.projecttitle,
            "lang_dial": y.languagedialogues,
            "genre": y.genre,
            "project_type": y.projecttype,
            "duration": y.duration,
            "project_status": y.projectstatus,
            "total_amount": payment_amount,
        }
        return render(request, "ideamall/auction_checkout.html", context)

    context = {
        "project_title": request.session["projecttitle"],
        "lang_dial": request.session["languagedialogues"],
        "genre": request.session["genre"],
        "project_type": request.session["projecttype"],
        "duration": request.session["duration"],
        "project_status": request.session["projectstatus"],
        "total_amount": request.session["total_amount"],
    }
    return render(request, "ideamall/auction_checkout.html", context)


def auction_checkoutpage(request):
    pass
    # return render(request, "ideamall/auction_checkout.html", context)


def detailpage(request, id):
    x = Showcase.objects.get(showcase_id=id)
    print('\n \n \n \n ************ blockchain ************ \n',
          x.onepageruploaded, '\n ****** \n', x)

    if x.findcowriter == True:
        print("Went into findcowriter condition")
        data = Make.objects.filter(
            lang_known=x.languagedialogues).exclude(user_id=request.user)
        context = {
            "data": x,
            "writers": data,
            "langua": x.languagedialogues,
        }
        return render(request, "ideamall/detailPage.html", context)
    # CurrentUser = User.objects.get(id=request.user.id)
    if x.numberofviewers.filter(id=request.user.id).exists():
        print("viewers exists")
        pass
    else:
        print("viewers not exists")
        x.numberofviewers.add(request.user.id)
    x.viewercount = len(x.numberofviewers.values())
    x.save()
    # if x.numberofviewers.all():
    #     found = 0
    #     for i in x.numberofviewer~s.all():
    #         if i.user_id == request.user:
    #             found = 1
    #             break
    #         else:
    #             found = 0
    #     if found == 1:
    #         pass
    #     else:
    #         x.numberofviewers.add(request.user)
    #     x.viewercount = len(x.numberofviewers.values())
    # else:
    #     x.numberofviewers.add(request.user)
    #     x.viewercount = 1
    # x.save()
    with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
        body = f.read()

    #! Blockchain start
    # key = x.projecttitle
    # # onepager
    # if x.onepageruploaded is not None:
    #     onepagerEncrypted = x.onepageruploaded
    #     x.onepageruploaded = ipfsUriDecrypt(key, onepagerEncrypted)
    #     print('\n \n \n onepager', onepagerEncrypted)

    # # storyuploaded
    # if x.storyuploaded is not None:
    #     storyuploaded = x.storyuploaded
    #     x.storyuploaded = ipfsUriDecrypt(key, storyuploaded)
    #     print('\n \n \n storyuploaded', storyuploaded)

    # # samplescriptuploaded
    # if x.samplescriptuploaded is not None:
    #     samplescriptuploadedencrypt = x.samplescriptuploaded
    #     x.samplescriptuploaded = ipfsUriDecrypt(
    #         key, samplescriptuploadedencrypt)
    #     print("\n \n \n samplescriptuploaded", samplescriptuploadedencrypt)

    # # fullscriptuploaded
    # if x.fullscriptuploaded is not None:
    #     fullscriptuploaded = x.fullscriptuploaded
    #     x.fullscriptuploaded = ipfsUriDecrypt(key, fullscriptuploaded)
    #     print("\n \n \n fullscriptuploaded", fullscriptuploaded)

    # # samplefootageuploaded
    # if x.samplefootageuploaded is not None:
    #     samplefootageuploaded = x.samplefootageuploaded
    #     x.samplefootageuploaded = ipfsUriDecrypt(key, samplefootageuploaded)
    #     print("samplefootageuploaded", samplefootageuploaded)

    # #  pitchdeckuploaded
    # if x.pitchdeckuploaded is not None:
    #     pitchdeckuploaded = x.pitchdeckuploaded
    #     x.pitchdeckuploaded = ipfsUriDecrypt(key, pitchdeckuploaded)
    #     print("pitchdeckuploaded", pitchdeckuploaded)

    # # samplenarrationuploaded
    # if x.samplenarrationuploaded is not None:
    #     samplenarrationuploaded = x.samplenarrationuploaded
    #     x.samplenarrationuploaded = ipfsUriDecrypt(
    #         key, samplenarrationuploaded)
    #     print("samplenarrationuploaded", samplenarrationuploaded)

    # # characterintrouploaded
    # if x.characterintrouploaded is not None:
    #     characterintrouploaded = x.characterintrouploaded
    #     x.characterintrouploaded = ipfsUriDecrypt(key, characterintrouploaded)
    #     print("characterintrouploaded", characterintrouploaded)

    # # scriptanalysisuploaded
    # if x.scriptanalysisuploaded is not None:
    #     scriptanalysisuploaded = x.scriptanalysisuploaded
    #     x.scriptanalysisuploaded = ipfsUriDecrypt(key, scriptanalysisuploaded)
    #     print("scriptanalysisuploaded", scriptanalysisuploaded)

    # # narratefulluploaded
    # if x.narratefulluploaded is not None:
    #     narratefulluploaded = x.narratefulluploaded
    #     x.narratefulluploaded = ipfsUriDecrypt(key, narratefulluploaded)
    #     print("narratefulluploaded", narratefulluploaded)

    # # ? Blockchain end

    context_email = {
        "Date": date.today(),
        "Name": x.user_id.email,
        "emailcode": "IM9",
        "heading1": "SIT UP!",
        "heading2": "Someone is interested in your idea!!",
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context\
    sendemailim(
        x.user_id.email,
        "Someone view your idea",
        date.today(),
        context_email,
    )

    context = {"data": x}
    return render(request, "ideamall/detailPage.html", context)


def contactforcowriting(request):
    if request.method == "POST":
        print("got till here")
        x = Showcase.objects.get(showcase_id=request.POST.get("comm_id"))
        print(x.genre, " :genre found")

        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": x.user_id.email,
            "emailcode": "IM18",
            "heading1": "AMAZING!",
            "heading2": "You have a new potential writing buddy!!",
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context\
        sendemailim(
            x.user_id.email,
            f"{request.user.email} view your cowriting idea",
            date.today(),
            context_email,
        )
        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": request.user.email,
            "emailcode": "IM19",
            "heading1": "BUCK UP!",
            "heading2": "Your interest in collaborative writing is communicated!!",
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context\
        sendemailim(
            request.user.email,
            "you interest for cowriting is conveyed",
            date.today(),
            context_email,
        )
        print("mail sent!")
        data = {"message": "Interest Communicated!",
                "id": request.POST.get("comm_id")}
        return JsonResponse(data)


def auctionpage(request):
    x = Auction.objects.all().exclude(auc_payment_done=False)

    for i in x:
        print(i, " : auction object")
        print(i.auction_view.all(), type(i.auction_view.all()))
        for j in i.auction_view.all():
            print(j.email, " : auction_user_view")

    ongoing = []
    upcoming = []
    past = []
    all_auc = []
    pre_future = []
    for i in x:

        if i.reserve_price == 0:
            continue
        else:
            if i.auction_end_date < date.today():
                # past.append(i)
                all_auc.append(i)
            else:
                # upcoming.append(i)
                all_auc.append(i)
                pre_future.append(i)

    # if len(past) > 0:
    #     past.reverse()
    # if len(upcoming) > 0:
    #     upcoming.reverse()
    # if len(ongoing) > 0:
    #     ongoing.reverse()
    if len(pre_future) > 0:
        pre_future.reverse()
    all_auc.reverse()
    global auction_pages
    auction_pages = request.GET.get("entries", auction_pages)
    per_page = auction_pages
    # paginator_past = Paginator(past, per_page)
    # paginator_present = Paginator(ongoing, per_page)
    # paginator_future = Paginator(upcoming, per_page)
    paginator_pre_future = Paginator(pre_future, per_page)

    paginator_all = Paginator(all_auc, per_page)
    page = request.GET.get("page")

    try:
        # paginated_past = paginator_past.get_page(page)
        # paginated_present = paginator_present.get_page(page)
        # paginated_future = paginator_future.get_page(page)
        paginated_pre_future = paginator_pre_future.get_page(page)

        paginated_all = paginator_all.get_page(page)
        # if len(past) >= len(ongoing) and len(past) >= len(upcoming):
        #     page_obj = paginator_past.get_page(page)
        # elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
        #     page_obj = paginator_future.get_page(page)
        # else:
        #     page_obj = paginator_present.get_page(page)
        page_obj = paginator_pre_future.get_page(page)

    except PageNotAnInteger:
        # paginated_past = paginator_past.get_page(1)
        # paginated_present = paginator_present.get_page(1)
        # paginated_future = paginator_future.get_page(1)
        paginated_pre_future = paginator_ore_future.get_page(1)

        paginated_all = paginator_all.get_page(1)
        # if len(past) >= len(ongoing) and len(past) >= len(upcoming):
        #     page_obj = paginator_past.get_page(1)
        # elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
        #     page_obj = paginator_future.get_page(1)
        # else:
        #     page_obj = paginator_present.get_page(1)
        page_obj = paginator_pre_future.get_page(1)

    except EmptyPage:
        # paginated_past = paginator_past.page(paginator_past.num_pages)
        # paginated_present = paginator_present.page(paginator_present.num_pages)
        paginated_pre_future = paginator_pre_future.page(
            paginator_pre_future.num_pages)
        # paginated_future = paginator_future.page(paginator_future.num_pages)
        paginated_all = paginator_all.page(paginator_all.num_pages)
        # if len(past) >= len(ongoing) and len(past) >= len(upcoming):
        #     page_obj = paginator_past.get_page(paginator_past.num_pages)
        # elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
        #     page_obj = paginator_future.get_page(paginator_future.num_pages)
        # else:
        #     page_obj = paginator_present.get_page(paginator_present.num_pages)
        page_obj = paginator_pre_future.get_page(
            paginator_pre_future.num_pages)
    # page_obj = paginator_all.get_page(paginator_all.num_pages)
    # print("passs")
    # print(type(paginated_present),paginated_present)
    # print(type(paginated_future),paginated_future)

    # page_display = paginated_present.extend(paginated_future)
    # print(page_display,"pagesss")
    context = {
        # "page_obj_past": paginated_past,
        # "page_obj_present": paginated_present,
        # "page_obj_future": paginated_future,
        "page_obj": page_obj,
        "page_obj_all": paginated_all,
        "present_future": paginated_pre_future
    }

    # context = {"ongoing": ongoing, "upcoming": upcoming, "past": past}
    return render(request, "ideamall/auctionpage.html", context)


def auctiondetails(request, id):
    x = Auction.objects.get(auction_id=id)
    if x.auction_view.filter(id=request.user.id).exists():
        print("viewers exists")
        pass
    else:
        print("viewers not exists")
        x.auction_view.add(request.user.id)
    x.auction_view_count = len(x.auction_view.values())
    x.save()
    context = {"data": x, "bid_button_visiblity": True}

    # x = Auction.objects.all()
    # y = []
    # for i in x:
    #     if str(i.auction_details.showcase_id) == str(id):
    #         y.append(i)
    #     else:
    #         continue
    # print(y, ": Chart")

    # context = {"data": y, "bid_button_visiblity": True}

    return render(request, "ideamall/bidnow.html", context)


def bidnow(request):
    # if the highest bid in the auction object is made by the same
    if request.method == "POST":
        y = Auction.objects.get(auction_id=request.POST.get("auctionid"))
        if y.winner == request.user:
            return HttpResponse("you are already a highest bidder")
        temp = y.next_possible_bid
        if float(y.next_possible_bid) < float(int(y.reserve_price) * 1.5):
            y.next_possible_bid = round(
                float(temp) + float(y.reserve_price) * 0.05, 2)
        elif float(y.next_possible_bid) > float(int(y.reserve_price) * 1.5) and float(
            y.next_possible_bid
        ) < float(int(y.reserve_price) * 2):
            y.next_possible_bid = round(
                float(temp) + float(y.reserve_price) * 0.1, 2)
        else:
            y.next_possible_bid = round(
                float(temp) + float(y.reserve_price) * 0.15, 2)
        # it should limit to only 2 decimal places
        # limiting to 2 decimal place
        y.highest_bid = temp
        prev_win = y.winner
        if y.winner != request.user:
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": y.auction_user.email,
                "emailcode": "IM31",
                "heading1": "CELEBRATE!",
                "heading2": str(y.auction_details.projecttitle)
                + " has become competitive!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                y.auction_user.email,
                "Auction become competetive",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user,
                "emailcode": "IM32",
                "heading1": "GLORIOUS!",
                "heading2": "your bid for"
                + str(y.auction_details.projecttitle)
                + " is unchallenged!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                request.user.email,
                "Your bid on Auction",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": y.winner,
                "emailcode": "IM33",
                "heading1": "GLORIOUS!",
                "heading2": "your bid for"
                + str(y.auction_details.projecttitle)
                + " is challenged!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                y.winner,
                "Auction get challenged",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
        y.winner = request.user
        y.no_of_bids = int(y.no_of_bids) + 1

        z = Bid()
        z.auction_linked = y
        z.bidder = request.user
        z.bid_currency = y.currency
        z.bid_amound = temp

        z.save()

        x = Bid.objects.filter(auction_linked=y).values("bidder").distinct()
        count_new_bidder = 0
        for i in x:
            count_new_bidder += 1
        y.no_of_bidders = count_new_bidder
        y.save()
        print("last mails mybid")
        x = Bid.objects.filter(auction_linked=y)
        for i in x:
            print("mubid for loop")
            print(y.winner, " winner ", prev_win, " prev winner")
            if i.bidder != y.winner and i.bidder != prev_win:
                print("mubid if condition")
                with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                    body = f.read()

                context_email = {
                    "Date": date.today(),
                    "Name": y.winner,
                    "emailcode": "IM34",
                    "heading1": "NOTICE!",
                    "heading2": "The auction for "
                    + str(y.auction_details.projecttitle)
                    + " is heating up!!",
                    "body": body,
                }
                # whomtosend, titleofmail, dateofemail, context\
                sendemail(
                    y.winner,
                    "Notice",
                    date.today(),
                    context_email,
                    EMAIL_HOST_USER,
                ).start()
        if y.no_of_bids == 1:
            print("checkim29")
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": y.auction_user.email,
                "emailcode": "IM29",
                "heading1": "SPLENDID!",
                "heading2": str(y.auction_details.projecttitle)
                + " has earned the first bid!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                y.auction_user.email,
                "first bid on your Auction",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM30",
                "heading1": "GLORIOUS!",
                "heading2": "your bid for"
                + str(y.auction_details.projecttitle)
                + " is unchallenged!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                request.user.email,
                "Your first bid on Auction",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
        print("mybid mails done")
        return redirect("mybid")


def mybid(request):
    # y = Bid.objects.filter(bidder=request.user)
    # print(y, " : compare values")
    x = (
        Bid.objects.filter(bidder=request.user)
        .values("auction_linked")
        .annotate(max_bid=Max("bid_amound"))
    )

    print(x, " : new values")
    data = Bid.objects.none()
    for i in x:
        t = Bid.objects.filter(
            auction_linked=i["auction_linked"],
            bid_amound=i["max_bid"],
            bidder=request.user,
        )
        data = data | t
    data = data.order_by("bid_on")
    print(data, "manojmybid datas")
    # auctionid = []
    # maxbid = []
    # for i in x:
    #     auctionid.append(i['auction_linked'])
    #     auctionid.append(i['auction_linked'])
    # print(l,"values")

    # # x = B
    #
    #
    #
    #
    #
    # id.objects.filter(bidder=request.user)
    # # print(x,"x value")
    global mybid_per_page
    paginate_by = request.GET.get("entries", mybid_per_page)
    mybid_per_page = paginate_by
    paginator = Paginator(data, mybid_per_page)
    page = request.GET.get("page")

    try:
        paginated = paginator.get_page(page)
    except PageNotAnInteger:
        paginated = paginator.get_page(1)
    except EmptyPage:
        paginated = paginator.page(paginator.num_pages)
    context = {"data": data, "page_obj": paginated}
    return render(request, "ideamall/mybid.html", context)


def shortlist2(request, pk):
    x = Commissioning.objects.get(pk=pk)
    if x:
        if request.user in x.shortlisted.all():
            x.shortlisted.remove(request.user)
            x.shortlist_count -= 1
            x.shortlisted_by_me = False
            liked = "F"
        else:
            x.shortlisted.add(request.user)
            x.shortlist_count += 1
            x.shortlisted_by_me = True
            liked = "T"
        x.save()
        data = {
            "status": True,
            "liked": liked,
            "shortlistcount": x.shortlist_count,
        }
    else:
        data = {
            "status": False,
            "message": "showcase Not Found",
        }
    return JsonResponse(data)


def shortlistshow(request, pk):
    x = Showcase.objects.get(pk=pk)
    if x:
        if request.user in x.showcase_shortlisted.all():
            x.showcase_shortlisted.remove(request.user)
            x.showcase_shortlist_count -= 1
            liked = "F"
        else:
            x.showcase_shortlisted.add(request.user)
            x.showcase_shortlist_count += 1
            liked = "T"
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM8",
                "heading1": "YAY YAY!",
                "heading2": "Someone has shortlisted your idea!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "shorlist idea",
                date.today(),
                context_email,
            )
        x.save()
        data = {
            "status": True,
            "liked": liked,
            "shortlistcount": x.showcase_shortlist_count,
        }
    else:
        data = {
            "status": False,
            "message": "showcase Not Found",
        }
    return JsonResponse(data)


def shortlistauc(request, pk):
    x = Auction.objects.get(pk=pk)
    if x:
        if request.user in x.auction_shortlisted.all():
            x.auction_shortlisted.remove(request.user)
            x.auction_shortlist_count -= 1
            liked = "F"
        else:
            x.auction_shortlisted.add(request.user)
            x.auction_shortlist_count += 1
            liked = "T"
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.auction_details.user_id,
                "emailcode": "IM27",
                "heading1": "YAY YAY!",
                "heading2": "Someone has shortlisted "
                + str(x.auction_details.projecttitle)
                + " Auction!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.auction_details.user_id.email,
                "shorlist Auction",
                date.today(),
                context_email,
            )
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM28",
                "heading1": "THANK YOU!",
                "heading2": "for being interested in "
                + str(x.auction_details.projecttitle)
                + " !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Auction Shortlisted",
                date.today(),
                context_email,
            )
        x.save()
        data = {
            "status": True,
            "liked": liked,
            "shortlistcount": x.auction_shortlist_count,
        }
    else:
        data = {
            "status": False,
            "message": "showcase Not Found",
        }
    return JsonResponse(data)


def likepremise(request, pk):
    x = Premisepool.objects.get(pk=pk)
    if x:
        if request.user in x.liked_by.all():
            x.liked_by.remove(request.user)
            x.no_of_likes -= 1
            liked = "F"
        else:
            x.liked_by.add(request.user)
            x.no_of_likes += 1
            liked = "T"
            with open(rf"{basepath}/lpp/templates/lpp/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.premise_user.first_name,
                "emailcode": "IM-1",
                "heading1": f"Yaay! Someone liked your premise {x.premise}",
                "heading2": "Congrats",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context, EMAIL_HOST_USER
            sendemail(
                x.premise_user.email,
                "Premise Liked!",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
        x.save()
        data = {
            "status": True,
            "liked": liked,
            "shortlistcount": x.no_of_likes,
        }
    else:
        data = {
            "status": False,
            "message": "showcase Not Found",
        }
    return JsonResponse(data)


def shortlist(request):
    x = Commissioning.objects.filter(commission_id=request.POST.get("starid"))
    for i in x:
        if i.shortlisted.filter(id=request.user.id).exists():
            print(request.user.id, ": shortlist2")
            i.shortlisted.remove(request.user.id)

        else:
            i.shortlisted.add(request.user.id)
        i.save()
    return redirect("oppor")


# def pageenter(request):
#     if request.method == "POST":
#         pages_list = request.POST.get('entries')
#     oppor(pages_list)


def dormant(request):
    x = Auction.objects.filter(auction_user=request.user)
    pending = []
    for i in x:
        if i.reserve_price == 0:
            pending.append(i)
    context = {"pending": pending}
    return render(request, "ideamall/Dormant.html", context)


def auctionurl(request):
    x = Auction.objects.filter(auction_user=request.user)
    lst = []
    for i in x:
        stringss = "http://115.246.78.132/ideamall/auctiondetails/" + \
            str(i.auction_id)
        lst.append(stringss)
    context = {"data": lst}
    return JsonResponse(context)

# check if any new bid received from last view or not


def checknewbidReceived(request):
    '''
    s = "2022-11-22 04:30:36.175000+00:00"
    a = s.split()
    t = a[0].split('-')
    year = t[0]
    month = t[1]
    date = t[2]
    y = a[1].split(':')
    hour = y[0]
    minute = y[1]
    print(year,month,date,hour,minute)
    '''
    context = {}
    if request.method == "POST":
        id = request.POST["id"]
        date = request.POST["date"]

        context = {}
        x = Bid.objects.filter(auction_linked=id).order_by("-bid_amound")
        for i in x:
            if i.bid_on - date > 0:
                context["result"] = True
                return HttpResponse(json.dumps(context), content_type="application/json")
        context["result"] = False
        return HttpResponse(json.dumps(context), content_type="application/json")
    return HttpResponse(json.dumps(context), content_type="application/json")


def myauction(request):
    # manoj
    temp1 = datetime.now()
    try:
        y = MyAuctionUserLoginDetails.objects.get(user=request.user)
        temp1 = y.previouslogin
        y.previouslogin = datetime.now()
        y.save()
    except:
        y = MyAuctionUserLoginDetails()
        if MyAuctionUserLoginDetails.objects.all().exists():
            y.id = int(MyAuctionUserLoginDetails.objects.all().last().id) + 1
        else:
            y.id = 1
        y.user = request.user
        y.previouslogin = datetime.now()
        temp1 = y.previouslogin
        y.save()

    x = Auction.objects.filter(auction_user=request.user).exclude(
        auc_payment_done=False
    )
    ongoing = []
    upcoming = []
    past = []
    pending = []
    newbid = []
    for i in x:
        if i.reserve_price == 0:
            pending.append(i)
        else:
            if i.auction_end_date < date.today():
                past.append(i)
            elif i.auction_start_date > date.today():
                upcoming.append(i)
            else:
                ongoing.append(i)

            p = Bid.objects.filter(
                auction_linked=i.auction_id).order_by("-bid_amound")
            for category in p:
                if category.bid_on > temp1:
                    newbid.append(str(i.auction_id))

    if len(past) > 0:
        past.reverse()
    if len(upcoming) > 0:
        upcoming.reverse()
    if len(ongoing) > 0:
        ongoing.reverse()
    global my_auction_pages
    my_auction_pages = request.GET.get("entries", my_auction_pages)
    per_page = my_auction_pages
    paginator_past = Paginator(past, per_page)
    paginator_present = Paginator(ongoing, per_page)
    paginator_future = Paginator(upcoming, per_page)
    page = request.GET.get("page")

    try:
        paginated_past = paginator_past.get_page(page)
        paginated_present = paginator_present.get_page(page)
        paginated_future = paginator_future.get_page(page)
        if len(past) >= len(ongoing) and len(past) >= len(upcoming):
            page_obj = paginator_past.get_page(page)
        elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
            page_obj = paginator_future.get_page(page)
        else:
            page_obj = paginator_present.get_page(page)
    except PageNotAnInteger:
        paginated_past = paginator_past.get_page(1)
        paginated_present = paginator_present.get_page(1)
        paginated_future = paginator_future.get_page(1)
        if len(past) >= len(ongoing) and len(past) >= len(upcoming):
            page_obj = paginator_past.get_page(1)
        elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
            page_obj = paginator_future.get_page(1)
        else:
            page_obj = paginator_present.get_page(1)
    except EmptyPage:
        paginated_past = paginator_past.page(paginator_past.num_pages)
        paginated_present = paginator_present.page(paginator_present.num_pages)
        paginated_future = paginator_future.page(paginator_future.num_pages)
        if len(past) >= len(ongoing) and len(past) >= len(upcoming):
            page_obj = paginator_past.get_page(paginator_past.num_pages)
        elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
            page_obj = paginator_future.get_page(paginator_future.num_pages)
        else:
            page_obj = paginator_present.get_page(paginator_present.num_pages)
    context = {
        "past": paginated_past,
        "ongoing": paginated_present,
        "upcoming": paginated_future,
        "page_obj": page_obj,
        "all_objects": x,
        "previous_login": temp1,
        "listofnewbidid": newbid,
    }

    # context = {
    #     "ongoing": ongoing,
    #     "upcoming": upcoming,
    #     "past": past,
    #     "pending": pending,
    # }
    return render(request, "ideamall/myauction.html", context)


def sendmailcowriter(request):
    if request.method == "POST":
        cowriter_id = request.POST.get("cowriter_id")
        cowriter_email = User.objects.get(email=cowriter_id)
        subject = "Do you want to colab?"
        from_email = settings.EMAIL_HOST_USER
        to = cowriter_email.email
        context = {
            "Date": date.today(),
            "Name": cowriter_email.first_name,
            "emailcode": "IM-2",
            "heading1": "I have a great idea on which we can work together.",
            "heading2": f"Mail me if you are interested! {request.user.email}",
            "body": "<p>This is the body!</p>",
        }
        html_content = render_to_string(
            rf"{basepath}/ideamall/templates/ideamall/email_templete.html",
            context,  # /home/user/mnf/project/MNF/ideamall/templates/ideamall/email_templete.html
        )  # render with dynamic value
        # Strip the html tag. So people can see the pure text at least.
        text_content = strip_tags(html_content)
        # create the email, and attach the HTML version as well.
        msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        data = {"response": "Interest Communicated"}
        return JsonResponse(data)


def emailtoauctioneer(request):
    if request.method == "POST":
        # send mail to auctioneer who created this showcase object
        x = Showcase.objects.get(showcase_id=request.POST.get("showcaseid"))
        x.people_interestd_in_partfull.add(request.user)
        x.save()
        if request.POST.get("fullfinancing"):
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": request.user.email,
                "emailcode": "IM24",
                "heading1": "LOOK OUT!",
                "heading2": "Your interest in fully financing "
                + str(x.projecttitle)
                + " is forwarded!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                request.user.email,
                "Full financing is conveyed",
                date.today(),
                context_email,
            )
            # to idea owner
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM23",
                "heading1": "KNOCK UP!",
                "heading2": str(x.projecttitle) + " has a potential partner!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Potential partner found",
                date.today(),
                context_email,
            )
        # save user object of person who shown interest so that mails can be interchanged
        # if on then he is interested in that type of financing otherwise off
        return True  # send mail using our email id with html embedded


def sameauctioneer(request, id):
    x = Auction.objects.filter(auction_user=id).exclude(auc_payment_done=False)
    ongoing = []
    upcoming = []
    past = []
    all_auc = []
    pre_future = []

    for i in x:
        if i.reserve_price == 0:
            continue
        else:
            if i.auction_end_date < date.today():
                # past.append(i)
                all_auc.append(i)
            # elif i.auction_start_date > date.today():
            #     upcoming.append(i)
            else:
                # ongoing.append(i)
                all_auc.append(i)
                pre_future.append(i)
    # if len(past) > 0:
    #     past.reverse()
    # if len(upcoming) > 0:
    #     upcoming.reverse()
    # if len(ongoing) > 0:
    #     ongoing.reverse()
    if len(pre_future) > 0:
        pre_future.reverse()
    all_auc.reverse()
    global sameauction_pages
    sameauction_pages = request.GET.get("entries", sameauction_pages)
    per_page = sameauction_pages
    # paginator_past = Paginator(past, per_page)
    # paginator_present = Paginator(ongoing, per_page)
    # paginator_future = Paginator(upcoming, per_page)
    paginator_pre_future = Paginator(pre_future, per_page)

    paginator_all = Paginator(all_auc, per_page)
    page = request.GET.get("page")

    try:
        # paginated_past = paginator_past.get_page(page)
        # paginated_present = paginator_present.get_page(page)
        # paginated_future = paginator_future.get_page(page)
        paginated_pre_future = paginator_pre_future.get_page(page)

        paginated_all = paginator_all.get_page(page)
        # if len(past) >= len(ongoing) and len(past) >= len(upcoming):
        #     page_obj = paginator_past.get_page(page)
        # elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
        #     page_obj = paginator_future.get_page(page)
        # else:
        #     page_obj = paginator_present.get_page(page)
        page_obj = paginator_pre_future.get_page(page)
    except PageNotAnInteger:
        # paginated_past = paginator_past.get_page(1)
        # paginated_present = paginator_present.get_page(1)
        # paginated_future = paginator_future.get_page(1)
        paginated_pre_future = paginator_ore_future.get_page(1)

        paginated_all = paginator_all.get_page(1)
        # if len(past) >= len(ongoing) and len(past) >= len(upcoming):
        #     page_obj = paginator_past.get_page(1)
        # elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
        #     page_obj = paginator_future.get_page(1)
        # else:
        #     page_obj = paginator_present.get_page(1)
        page_obj = paginator_pre_future.get_page(1)
    except EmptyPage:
        # paginated_past = paginator_past.page(paginator_past.num_pages)
        # paginated_present = paginator_present.page(paginator_present.num_pages)
        paginated_pre_future = paginator_pre_future.page(
            paginator_pre_future.num_pages)
        # paginated_future = paginator_future.page(paginator_future.num_pages)
        paginated_all = paginator_all.page(paginator_all.num_pages)
        # if len(past) >= len(ongoing) and len(past) >= len(upcoming):
        #     page_obj = paginator_past.get_page(paginator_past.num_pages)
        # elif len(upcoming) >= len(ongoing) and len(upcoming) >= len(past):
        #     page_obj = paginator_future.get_page(paginator_future.num_pages)
        # else:
        #     page_obj = paginator_present.get_page(paginator_present.num_pages)
        page_obj = paginator_pre_future.get_page(
            paginator_pre_future.num_pages)
    context = {
        # "page_obj_past": paginated_past,
        # "page_obj_present": paginated_present,
        # "page_obj_future": paginated_future,
        "page_obj": page_obj,
        "page_obj_all": paginated_all,
        "present_future": paginated_pre_future
    }
    return render(request, "ideamall/auctionpage.html", context)


def emailfordownload(request):
    if request.method == "POST":
        x = Showcase.objects.get(showcase_id=request.POST.get("showcaseid"))
        if request.POST.get("downactions") == "one_pager":

            print("one_pager_if_mail")
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM10",
                "heading1": "WATCH OUT!",
                "heading2": "Someone is reading " + str(x.projecttitle) + " onepager!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "One pager interest",
                date.today(),
                context_email,
            )
        elif request.POST.get("downactions") == "story":

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM11",
                "heading1": "CHEER UP!",
                "heading2": "Someone is weighing" + str(x.projecttitle) + " !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Story interest",
                date.today(),
                context_email,
            )
        elif request.POST.get("downactions") == "sample_script":

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM12",
                "heading1": "REJOICE!",
                "heading2": str(x.projecttitle) + "  is attracting people!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Sample script interest",
                date.today(),
                context_email,
            )
        elif request.POST.get("downactions") == "full_script":

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM103",
                "heading1": "BRAVO!",
                "heading2": "Somone is eager on " + str(x.projecttitle) + " !!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Full script interest",
                date.today(),
                context_email,
            )
        elif request.POST.get("downactions") == "sample_footage":

            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": x.user_id.email,
                "emailcode": "IM14",
                "heading1": "ALAS!",
                "heading2": str(x.projecttitle) + " may get completed soon!!",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemailim(
                x.user_id.email,
                "Sample footage interest",
                date.today(),
                context_email,
            )
        return redirect("oppor")


def history(request, id):
    # if request.method == "POST":
    # x = Bid.objects.filter(auction_linked=request.POST.get("auc_id")).order_by('-bid_amound')
    x = Bid.objects.filter(auction_linked=id).order_by("-bid_amound")
    y = Auction.objects.get(auction_id=id)
    today = date.today()
    print(y, " : Auction object")
    context = {"data": x, "auc_details": y, "date": today}
    # print(x, " : bid object")
    # return HttpResponseRedirect("ideamall/history.html", context)
    return render(request, "ideamall/history.html", context)


def deleteauction(request, id):
    x = Auction.objects.get(auction_id=id)
    x.delete()
    return redirect("dormant")


def comparepremise(new, other):
    pattern = re.compile(r'\s+')
    t = re.sub(pattern, '', new)
    u = re.sub(pattern, '', other)
    if t == u:
        return True
    return False


def try1(request):
    start_time = time.time()
    y = Premisepool.objects.all().order_by("-added_on")
    print("Time Taken: ",time.time() - start_time
          )
    return render(request, "ideamall/lop.html",context={"data":y})


def premisespool(request):
    import timeit
    if request.method == "POST":
        # y = Premisepool.objects.all().order_by("-premise_id")[0]
        all = Premisepool.objects.all()
        new = "What if " + str(request.POST.get("premisewhatif")) + "?"
        for i in all:
            res = comparepremise(new, i.premise)
            if res is True:
                if request.POST.get('calledfromajax') == "true":
                    return JsonResponse({"message": "True"})
                else:
                    print("premises else condition")
                    # messages.success(request, "Premise already exists")
                    return HttpResponse("premise already exists")

        x = Premisepool()
        x.premise_user = request.user
        try:
            y = Premisepool.objects.all().order_by("-added_on")[0]
            x.premise_no = int(y.premise_no) + 1
        except:
            x.premise_no = 1
        x.premise = "What if " + str(request.POST.get("premisewhatif")) + "?"
        if request.POST.get("primeseuser") == "something":
            x.primeseuser = request.user.first_name
            print(request.user.first_name, "first_name_premise")
        else:
            if request.POST.get("flag_fnname") == "Yes":
                z = User.objects.get(id=request.user.id)
                z.first_name = request.POST.get("primeseuser")
                z.save()
                cd = centralDatabase.objects.get(user_id=request.user)
                cd.firstName = z.first_name
                cd.save()
                x.primeseuser = request.POST.get("primeseuser")
        x.save()

        # send premisepool mail
        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": x.premise_user.first_name,
            "emailcode": "IM-10",
            "heading1": f"Thanks for adding premise {x.premise}",
            "heading2": "We hope that people will like it!",
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context, EMAIL_HOST_USER
        sendemail(
            x.premise_user.email,
            "Premise added successfully!",
            date.today(),
            context_email,
            EMAIL_HOST_USER,
        ).start()

        return redirect("premisespool")
    start_time1 = time.time()
    y = Premisepool.objects.all().order_by("-added_on")
    global premises_per_page
    paginate_by = request.GET.get("entries", premises_per_page)
    premises_per_page = paginate_by
    paginator = Paginator(y, premises_per_page)
    page = request.GET.get("page")
    print("Time Taken1: ", time.time() - start_time1)
    start_time = time.time()
    try:
        paginated = paginator.get_page(page)
    except PageNotAnInteger:
        paginated = paginator.get_page(1)
    except EmptyPage:
        paginated = paginator.page(paginator.num_pages)
    try:
        first = list(paginated)[0].premise_no
    except:
        first = 0
    try:
        last = list(paginated)[-1].premise_no
    except:
        last = 0

    print("Time Taken2: ", time.time() - start_time)
    context = {
        "data": paginated,
        "total": len(y),
        "entriesofPage": len(paginated),
        "first": first,
        "last": last,
    }
    return render(request, "ideamall/premisespool.html", context)


def deletepremisepool(request, id):
    x = Premisepool.objects.get(premise_id=id)
    if x.premise_user == request.user:
        x.delete()
    return redirect("premisespool")


def editpremise(request):
    if request.method == "POST":
        x = Premisepool.objects.get(premise_id=request.POST.get("id"))
        all = Premisepool.objects.all()
        new = "What if " + str(request.POST.get("premisewhatif")) + "?"
        for i in all:
            res = comparepremise(new, i.premise)
            if res is True:
                return JsonResponse({"message": "True"})
        if x.premise_user == request.user:
            x.premise = "What if " + \
                str(request.POST.get("premisewhatif")) + "?"
            x.save()
    return redirect("premisespool")


def contact_premise(request):
    if request.method == "POST":
        print("Premise request")
        x = Premisepool.objects.get(premise_id=request.POST.get("pid"))
        subject = "Someone shown interest in your premise!"
        from_email = settings.EMAIL_HOST_USER
        to = x.premise_user.email
        context = {
            "Date": date.today(),
            "pemail": x.premise_user.email,
            "Name": request.user.email,
            "emailcode": request.user.email,
            "heading1": " IM13 is Interested in your ",
            "heading2": "premise: " + '''"''' + str(x.premise) + '''"''',
        }
        html_content = render_to_string(
            rf"{basepath}/ideamall/templates/ideamall/email_tem103.html",
            context,  # /home/user/mnf/project/MNF/ideamall/templates/ideamall/email_templete.html
        )  # render with dynamic value
        # Strip the html tag. So people can see the pure text at least.
        text_content = strip_tags(html_content)
        # create the email, and attach the HTML version as well.
        msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        response = {"message": "Connection Request Sent Successfully!"}
    return JsonResponse(response)
    # return HttpResponse("Connection Request Sent Successfully!")


def rate_auction(request):
    if request.method == "POST":
        res = 0
        x = Showcase.objects.get(showcase_id=request.POST.get("id"))
        print(x, "showcaseinterest")
        if Showcaseinteraction.objects.filter(
            interaction_showcase=x, associated_user=request.user
        ):
            print("rate_auc_if_condition")
            y = Showcaseinteraction.objects.filter(
                interaction_showcase=x, associated_user=request.user
            )
            for i in y:
                temp = float(x.total_rating) - float(i.my_rating)
                i.my_rating = int(request.POST.get("ratings"))
                x.total_rating = temp + float(i.my_rating)
                i.save()

        else:
            print("rate_auc_else_condition")
            y = Showcaseinteraction()
            t = int(request.POST.get("ratings"))
            y.my_rating = t
            y.associated_user = request.user
            y.interaction_showcase = x
            ans = float(x.total_rating) + float(t)
            print(ans, ":ans_else_condition")
            x.total_rating = ans
            y.save()
            x.rated_by.add(request.user)
        print("rate_auc_rate_by")
        print("json_res")
        x.rating = x.total_rating / x.rated_by.count()
        x.save()
        context = {"total": x.rating}
        print("rate_auc_context")
        return JsonResponse(context)


def send_Bank_detail(request):
    bank_name = request.POST.get("bank_name")
    account_holder = request.POST.get("account_holder")
    ifsc = request.POST.get("ifsc")
    account_number = request.POST.get("account_number")
    branch = request.POST.get("branch")
    x = Commissioning.objects.get(commission_id=request.POST.get("idd"))
    body = (
        "Bank name: "
        + str(bank_name)
        + "    Account holders name: "
        + str(account_holder)
    )
    (
        +"    IFSC code: "
        + str(ifsc)
        + "    Account number: "
        + str(account_number)
        + "    Branch: "
        + str(branch)
    )
    # with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
    #             body = f.read()

    context_email = {
        "Date": date.today(),
        "Name": x.user_id.email,
        "emailcode": "to be decided",
        "heading1": "to be decided",
        "heading2": str(request.user)
        + "has sended a bank details for"
        + str(x.commission_string),
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context
    sendemail(
        x.user_id.email,
        "Recieved a bank details",
        date.today(),
        context_email,
        EMAIL_HOST_USER,
    ).start()
    return HttpResponse("details sended")


def message(request):
    message = request.POST.get("message")
    x = Commissioning.objects.get(commission_id=request.POST.get("idd"))
    body = str(message)
    # with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
    #             body = f.read()

    context_email = {
        "Date": date.today(),
        "Name": x.user_id.email,
        "emailcode": "to be decided",
        "heading1": "to be decided",
        "heading2": "Someone has messaged you for " + str(x.commission_string),
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context
    sendemail(
        x.user_id.email,
        "Recieved a message",
        date.today(),
        context_email,
        EMAIL_HOST_USER,
    ).start()
    return HttpResponse("message sended")


def messagecom(request):
    message = request.POST.get("message")
    # x = Commissioning.objects.get(maker=maker_id)
    x = Commissioning.objects.get(maker=request.POST.get("makeid"))
    y = Make.objects.get(uid=request.POST.get("makeid"))
    body = str(message)
    # with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
    #             body = f.read()
    print(y.user_id.email, "messagecom email")
    print(x.commission_string, "messagecom string")
    context_email = {
        "Date": date.today(),
        "Name": y.user_id,
        "emailcode": "to be decided",
        "heading1": "to be decided",
        "heading2": "Someone has messaged you for " + str(x.commission_string),
        "body": body,
    }
    # whomtosend, titleofmail, dateofemail, context
    sendemail(
        y.user_id.email,
        "Recieved a message",
        date.today(),
        context_email,
        EMAIL_HOST_USER,
    ).start()
    return HttpResponse("message sended")


def customnda(request, id):
    x = Auction.objects.get(auction_id=id)
    template = get_template("ideamall/nda.html")
    context = {
        "projecttitle": x.auction_details.projecttitle,
        "logline": x.auction_details.loglines,
        "dialogue_lang": x.auction_details.languagedialogues,
        "actionlines": x.auction_details.languageactionlines,
        "projecttype": x.auction_details.projecttype,
        "duration": x.auction_details.duration,
        "genre": x.auction_details.genre,
        "time": x.auction_details.setintime,
        "geography": x.auction_details.setingeography,
        "currency": x.auction_details.budgetcurrency,
        "amount": x.auction_details.budgetamount,
        "status": x.auction_details.projectstatus,
        "user": request.user,
    }
    html = template.render(context)
    pdf = render_to_pdf("ideamall/nda.html", context)
    if pdf:
        response = HttpResponse(pdf, content_type="application/pdf")
        filename = "nda_%s.pdf" % (context["projecttitle"])
        content = context["projecttitle"] + ".pdf"
        download = request.GET.get("download")
        if download:
            content = context["projecttitle"] + ".pdf"
        response["content-disposition"] = content
        return response
    return HttpResponse("NDA not found")


def datascript(request):
    print(
        "*******************-------------------------11111111111111111111111111**********---------------------"
    )
    lang12 = request.POST.get("firstlang")
    df = pd.read_csv(rf"{basepath}/lpp/scripts.csv")
    lang1 = str(lang12)
    if lang1 == "":
        lang1 = "English"
    print(lang1, " : languages :: types : ", type(lang1))

    list1_d = df.loc[df[lang1] == "D", "Script"].tolist()
    print("Bakery 20.1: ", list1_d)
    list1_y = df.loc[df[lang1] == "Y", "Script"].tolist()
    print("Bakery 20.2: ", list1_y)
    list1_dy = list1_d + list1_y

    # data = {}
    return JsonResponse({"data": list1_dy})


country_name = {
    "af": "Afghanistan",
    "al": "Albania",
    "dz": "Algeria",
    "ad": "Andorra",
    "ao": "Angola",
    "ai": "Anguilla",
    "ag": "Antigua and Barbuda",
    "ar": "Argentina",
    "am": "Armenia",
    "aw": "Aruba",
    "au": "Australia",
    "at": "Austria",
    "az": "Azerbaijan",
    "bs": "Bahamas",
    "bh": "Bahrain",
    "bd": "Bangladesh",
    "bb": "Barbados",
    "by": "Belarus",
    "be": "Belgium",
    "bz": "Belize",
    "bj": "Benin",
    "bm": "Bermuda",
    "bt": "Bhutan",
    "bo": "Bolivia",
    "ba": "Bosnia and Herzegovina",
    "bw": "Botswana",
    "br": "Brazil",
    "bn": "Brunei Darussalam",
    "bg": "Bulgaria",
    "bf": "Burkina Faso",
    "bi": "Burundi",
    "kh": "Cambodia",
    "cm": "Cameroon",
    "ca": "Canada",
    "cv": "Cape Verde",
    "ky": "Cayman Islands",
    "cf": "Central African Republic",
    "td": "Chad",
    "cl": "Chile",
    "cn": "China",
    "cx": "Christmas Island",
    "cc": "Cocos (Keeling) Islands",
    "co": "Colombia",
    "km": "Comoros",
    "cg": "Congo",
    "ck": "Cook Islands",
    "cr": "Costa Rica",
    "ci": "Cote DIvoire (Ivory Coast)",
    "hr": "Croatia (Hrvatska)",
    "cu": "Cuba",
    "cy": "Cyprus",
    "cz": "Czech Republic",
    "cd": "Democratic Republic of the Congo",
    "dk": "Denmark",
    "dj": "Djibouti",
    "dm": "Dominica",
    "do": "Dominican Republic",
    "ec": "Ecuador",
    "eg": "Egypt",
    "sv": "El Salvador",
    "gq": "Equatorial Guinea",
    "er": "Eritrea",
    "ee": "Estonia",
    "et": "Ethiopia",
    "fk": "Falkland Islands (Malvinas)",
    "fo": "Faroe Islands",
    "fm": "Federated States of Micronesia",
    "fj": "Fiji",
    "fi": "Finland",
    "fr": "France",
    "gf": "French Guiana",
    "pf": "French Polynesia",
    "tf": "French Southern Territories",
    "ga": "Gabon",
    "gm": "Gambia",
    "ge": "Georgia",
    "de": "Germany",
    "gh": "Ghana",
    "gi": "Gibraltar",
    "gb": "Great Britain (UK)",
    "gr": "Greece",
    "gl": "Greenland",
    "gd": "Grenada",
    "gp": "Guadeloupe",
    "gt": "Guatemala",
    "gn": "Guinea",
    "gw": "Guinea-Bissau",
    "gy": "Guyana",
    "ht": "Haiti",
    "hn": "Honduras",
    "hk": "Hong Kong",
    "hu": "Hungary",
    "is": "Iceland",
    "in": "India",
    "id": "Indonesia",
    "ir": "Iran",
    "iq": "Iraq",
    "ie": "Ireland",
    "il": "Israel",
    "it": "Italy",
    "jm": "Jamaica",
    "jp": "Japan",
    "jo": "Jordan",
    "kz": "Kazakhstan",
    "ke": "Kenya",
    "ki": "Kiribati",
    "kp": "Korea (North)",
    "kr": "Korea (South)",
    "kw": "Kuwait",
    "kg": "Kyrgyzstan",
    "la": "Laos",
    "lv": "Latvia",
    "lb": "Lebanon",
    "ls": "Lesotho",
    "lr": "Liberia",
    "ly": "Libya",
    "li": "Liechtenstein",
    "lt": "Lithuania",
    "lu": "Luxembourg",
    "mo": "Macao",
    "mk": "Macedonia",
    "mg": "Madagascar",
    "mw": "Malawi",
    "my": "Malaysia",
    "mv": "Maldives",
    "ml": "Mali",
    "mt": "Malta",
    "mh": "Marshall Islands",
    "mq": "Martinique",
    "mr": "Mauritania",
    "mu": "Mauritius",
    "yt": "Mayotte",
    "mx": "Mexico",
    "md": "Moldova",
    "mc": "Monaco",
    "mn": "Mongolia",
    "ms": "Montserrat",
    "ma": "Morocco",
    "mz": "Mozambique",
    "mm": "Myanmar",
    "na": "Namibia",
    "nr": "Nauru",
    "np": "Nepal",
    "nl": "Netherlands",
    "an": "Netherlands Antilles",
    "nc": "New Caledonia",
    "nz": "New Zealand (Aotearoa)",
    "ni": "Nicaragua",
    "ne": "Niger",
    "ng": "Nigeria",
    "nu": "Niue",
    "nf": "Norfolk Island",
    "mp": "Northern Mariana Islands",
    "no": "Norway",
    "gg": "NULL",
    "om": "Oman",
    "pk": "Pakistan",
    "pw": "Palau",
    "ps": "Palestinian Territory",
    "pa": "Panama",
    "pg": "Papua New Guinea",
    "py": "Paraguay",
    "pe": "Peru",
    "ph": "Philippines",
    "pn": "Pitcairn",
    "pl": "Poland",
    "pt": "Portugal",
    "qa": "Qatar",
    "re": "Reunion",
    "ro": "Romania",
    "ru": "Russian Federation",
    "rw": "Rwanda",
    "gs": "S. Georgia and S. Sandwich Islands",
    "sh": "Saint Helena",
    "kn": "Saint Kitts and Nevis",
    "lc": "Saint Lucia",
    "pm": "Saint Pierre and Miquelon",
    "vc": "Saint Vincent and the Grenadines",
    "ws": "Samoa",
    "sm": "San Marino",
    "st": "Sao Tome and Principe",
    "sa": "Saudi Arabia",
    "sn": "Senegal",
    "sc": "Seychelles",
    "sl": "Sierra Leone",
    "sg": "Singapore",
    "sk": "Slovakia",
    "si": "Slovenia",
    "sb": "Solomon Islands",
    "so": "Somalia",
    "za": "South Africa",
    "es": "Spain",
    "lk": "Sri Lanka",
    "sd": "Sudan",
    "sr": "Suriname",
    "sj": "Svalbard and Jan Mayen",
    "sz": "Swaziland",
    "se": "Sweden",
    "ch": "Switzerland",
    "sy": "Syria",
    "tw": "Taiwan",
    "tj": "Tajikistan",
    "tz": "Tanzania",
    "th": "Thailand",
    "tg": "Togo",
    "tk": "Tokelau",
    "to": "Tonga",
    "tt": "Trinidad and Tobago",
    "tn": "Tunisia",
    "tr": "Turkey",
    "tm": "Turkmenistan",
    "tc": "Turks and Caicos Islands",
    "tv": "Tuvalu",
    "ug": "Uganda",
    "ua": "Ukraine",
    "ae": "United Arab Emirates",
    "us": "United States of America",
    "uy": "Uruguay",
    "uz": "Uzbekistan",
    "vu": "Vanuatu",
    "ve": "Venezuela",
    "vn": "Viet Nam",
    "vg": "Virgin Islands (British)",
    "vi": "Virgin Islands (U.S.)",
    "wf": "Wallis and Futuna",
    "eh": "Western Sahara",
    "ye": "Yemen",
    "zr": "Zaire (former)",
    "zm": "Zambia",
    "zw": "Zimbabwe",
}

# * Fetch from Blockchain


def fetch_from_blockchain(request):
    if request.POST:

        email = request.user.email
        file_type = request.POST.get('file_type')
        project_title = request.POST.get('project_title')
        time_stamp = request.POST.get('time_stamp')
        url = fetchFromBlockchain(file_type, email, project_title, time_stamp)
        context = {
            'cid': url,
            'service': file_type
        }
        return render(request, 'ideamall/Blockchain.html', context)

    return render(request, 'ideamall/Blockchain.html')


def verfyFromBlockchain(request):
    if request.method == "POST":
        User_name = request.POST.get('User_name')
        fileFrom = request.POST.get('project_title')
        timeStamp = request.POST.get('time_stamp')
        result = verifyFromBlockchain(User_name, fileFrom, timeStamp)
        context = {
            'verify': result
        }

        return render(request, 'ideamall/Blockchain.html', context)
    return render(request, 'ideamall/Blockchain.html')


@login_required(login_url="/")
def commisioner_response(request, id):
    if request.method == "POST":
        obj = blockpermission.objects.get(blockpermission_id=id)
        file = request.POST.get("files")
        formats = request.POST.get("types")
        if formats == "Accept":
            if file == "sample_script":
                obj.sample_script = 1
                obj.sample_script_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "full_script":
                obj.full_script = 1
                obj.full_script_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "onepager":
                obj.onepager = 1
                obj.onepager_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "story":
                obj.story = 1
                obj.story_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "sample_footage":
                obj.sample_footage = 1
                obj.sample_footage_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "sample_narration":
                obj.sample_narration = 1
                obj.sample_narration_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "character_introduction":
                obj.character_introduction = 1
                obj.character_introduction_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "script_analysis":
                obj.script_analysis = 1
                obj.script_analysis_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "narrated_full_script":
                obj.narrated_full_script = 1
                obj.narrated_full_script_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "pitchdeck":
                obj.pitchdeck = 1
                obj.pitchdeck_date = date.today() + timedelta(days=2)
                obj.save()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": obj.user_id.email,
                "emailcode": "IM501",
                "heading1": "Congratulations!!",
                "heading2": f"{obj.related_showcase.user_id} accepted you to download {file} of {obj.related_showcase.projecttitle}",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                obj.user_id.email,
                "Someone accepted your request to download the file",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()

        elif formats == "Reject":
            if file == "sample_script":
                obj.sample_script = 2
                obj.sample_script_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "full_script":
                obj.full_script = 2
                obj.full_script_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "onepager":
                obj.onepager = 2
                obj.onepager_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "story":
                obj.story = 2
                obj.story_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "sample_footage":
                obj.sample_footage = 2
                obj.sample_footage_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "sample_narration":
                obj.sample_narration = 2
                obj.sample_narration_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "character_introduction":
                obj.character_introduction = 2
                obj.character_introduction_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "script_analysis":
                obj.script_analysis = 2
                obj.script_analysis_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "narrated_full_script":
                obj.narrated_full_script = 2
                obj.narrated_full_script_date = date.today() + timedelta(days=2)
                obj.save()
            if file == "pitchdeck":
                obj.pitchdeck = 2
                obj.pitchdeck_date = date.today() + timedelta(days=2)
                obj.save()
            with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
                body = f.read()

            context_email = {
                "Date": date.today(),
                "Name": obj.user_id.first_name,
                "emailcode": "IM502",
                "heading1": "Ah!",
                "heading2": f"{obj.related_showcase.user_id} has rejected you to download {file} of {obj.related_showcase.projecttitle}. You can re-ask after 2 days.",
                "body": body,
            }
            # whomtosend, titleofmail, dateofemail, context\
            sendemail(
                obj.user_id.email,
                "Someone Rejected your request to download the file",
                date.today(),
                context_email,
                EMAIL_HOST_USER,
            ).start()
        return True
    obj = blockpermission.objects.get(blockpermission_id=id)
    if request.user == obj.related_showcase.user_id:
        context = {"obj": obj}
        return render(request, "ideamall/permission.html", context)
    else:
        return HttpResponse("You are not authorized to access this page.")


def accept_reject(value, datee, permitted, file):
    if permitted.user_id == permitted.related_showcase.user_id:
        value = 1
        datee = date.today()
    if value == 0:
        return ["Your request for downloading is already shared.", 0]
    if value == -1:
        with open(rf"{basepath}/ideamall/templates/ideamall/body.txt") as f:
            body = f.read()

        context_email = {
            "Date": date.today(),
            "Name": permitted.related_showcase.user_id.email,
            "emailcode": "IM500",
            "heading1": str(permitted.user_id) + " is interested in checking" + str(file)+" of " + str(permitted.related_showcase.projecttitle),
            "heading2": "Kindly Grant Permission by clicking here: http://115.246.78.132/ideamall/permission/" + str(permitted.blockpermission_id),
            "body": body,
        }
        # whomtosend, titleofmail, dateofemail, context\
        sendemail(
            permitted.related_showcase.user_id.email,
            f"{permitted.user_id} Showed interest in {permitted.related_showcase.projecttitle}",
            date.today(),
            context_email,
            EMAIL_HOST_USER,
        ).start()
        return ["You are not allowed to download the file, mail has been send to give permission.", 0]
        # send mail to ask
    elif value == 1:
        if datee >= date.today():
            if file == "sample_script":
                samplescriptuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.samplescriptuploaded)
                # if res[1] == 1:
                #    return res[0]
                return [samplescriptuploaded, 1]
            if file == "full_script":
                fullscriptuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.fullscriptuploaded)
                return [fullscriptuploaded, 1]
            if file == "one_pager":
                onepageruploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.onepageruploaded)
                return [onepageruploaded, 1]
            if file == "story":
                storyuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.storyuploaded)
                print(storyuploaded, "storyuploadeddecrypt")
                return [storyuploaded, 1]
            if file == "sample_footage":
                samplefootageuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.samplefootageuploaded)
                return [samplefootageuploaded, 1]
            if file == "sample_narration":
                samplenarrationuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.samplenarrationuploaded)
                return [samplenarrationuploaded, 1]
            if file == "character_introduction":
                characterintrouploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.characterintrouploaded)
                return [characterintrouploaded, 1]
            if file == "script_analysis":
                scriptanalysisuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.scriptanalysisuploaded)
                return [scriptanalysisuploaded, 1]
            if file == "narrated_full_script":
                narratefulluploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.narratefulluploaded)
                return [narratefulluploaded, 1]
            if file == "pitchdeck":
                pitchdeckuploaded = ipfsUriDecrypt(
                    permitted.related_showcase.projecttitle, permitted.related_showcase.pitchdeckuploaded)
                return [pitchdeckuploaded, 1]
            # Decrypt and Download Presentation
        else:
            if file == "sample_script":
                permitted.sample_script = 0
                permitted.sample_script_date = date.today()
                permitted.save()
            if file == "full_script":
                permitted.full_script = 0
                permitted.full_script_date = date.today()
                permitted.save()
            if file == "one_pager":
                permitted.onepager = 0
                permitted.onepager_date = date.today()
                permitted.save()
            if file == "story":
                permitted.story = 0
                permitted.story_date = date.today()
                permitted.save()
            if file == "sample_footage":
                permitted.sample_footage = 0
                permitted.sample_footage_date = date.today()
                permitted.save()
            if file == "sample_narration":
                permitted.sample_narration = 0
                permitted.sample_narration_date = date.today()
                permitted.save()
            if file == "character_introduction":
                permitted.character_introduction = 0
                permitted.character_introduction_date = date.today()
                permitted.save()
            if file == "script_analysis":
                permitted.script_analysis = 0
                permitted.script_analysis_date = date.today()
                permitted.save()
            if file == "narrated_full_script":
                permitted.narrated_full_script = 0
                permitted.narrated_full_script_date = date.today()
                permitted.save()
            if file == "pitchdeck":
                permitted.pitchdeck = 0
                permitted.pitchdeck_date = date.today()
                permitted.save()
            t = date.today()
            accept_reject(0, t, permitted, file)
    elif value == 2:
        # rejected message
        if datee >= date.today():
            rep = "Commissioner has rejected your offer to download " + \
                str(file) + ". you can ask again after " + \
                str(datee-date.today()).split(' ')[0] + " days."
            return [rep, 2]

        if file == "sample_script":
            permitted.sample_script = 0
            permitted.sample_script_date = date.today()
            permitted.save()
        if file == "full_script":
            permitted.full_script = 0
            permitted.full_script_date = date.today()
            permitted.save()
        if file == "one_pager":
            permitted.onepager = 0
            permitted.onepager_date = date.today()
            permitted.save()
        if file == "story":
            permitted.story = 0
            permitted.story_date = date.today()
            permitted.save()
        if file == "sample_footage":
            permitted.sample_footage = 0
            permitted.sample_footage_date = date.today()
            permitted.save()
        if file == "sample_narration":
            permitted.sample_narration = 0
            permitted.sample_narration_date = date.today()
            permitted.save()
        if file == "character_introduction":
            permitted.character_introduction = 0
            permitted.character_introduction_date = date.today()
            permitted.save()
        if file == "script_analysis":
            permitted.script_analysis = 0
            permitted.script_analysis_date = date.today()
            permitted.save()
        if file == "narrated_full_script":
            permitted.narrated_full_script = 0
            permitted.narrated_full_script_date = date.today()
            permitted.save()
        if file == "pitchdeck":
            permitted.pitchdeck = 0
            permitted.pitchdeck_date = date.today()
            permitted.save()
            t = date.today()
        accept_reject(0, t, permitted, file)


def blockchainpermit(request):
    if request.method == "POST":
        file = request.POST.get("file")
        sid = request.POST.get("sid")
        show = Showcase.objects.get(showcase_id=sid)

        # CHECK WHETHER THE USER IS PRE-APPROVED BY SHOWCASER
        if file == "sample_script":
            what_is_the_permission = show.whocansee_samplescript
        elif file == "story":
            what_is_the_permission = show.whocansee_story
        elif file == "full_script":
            what_is_the_permission = show.whocansee_fullscript
        elif file == "one_pager":
            what_is_the_permission = show.whocansee_onepager
        elif file == "sample_footage":
            what_is_the_permission = show.whocansee_samplefootage
        elif file == "sample_narration":
            what_is_the_permission = show.whocansee_samplenarration
        elif file == "character_introduction":
            what_is_the_permission = show.whocansee_charintroduction
        elif file == "script_analysis":
            what_is_the_permission = show.whocansee_scriptanalysis
        elif file == "narrated_full_script":
            what_is_the_permission = show.whocansee_fullnarration
        elif file == "pitchdeck":
            what_is_the_permission = show.whocansee_pitchdeck

        if what_is_the_permission == "noone":
            run_permission_code = True
        elif what_is_the_permission == "anyone":
            run_permission_code = False
        elif what_is_the_permission == "any_auction_bidder":
            run_permission_code = False if Bid.objects.filter(
                bidder=request.user).exists() else True
        elif what_is_the_permission == "signing_nda":
            run_permission_code = True
            # Need more clarifications implementation wise. Unable to find Model class.
        elif what_is_the_permission == "shortlisted_idea":
            if request.user in show.showcase_shortlisted.all():
                run_permission_code = False
            else:
                run_permission_code = True
        elif what_is_the_permission == "interested_in_coproducing":
            run_permission_code = True
            # We are not saving interested in co-producing data in any models
        elif what_is_the_permission == "interested_in_fullfinancing":
            run_permission_code = True
            # We are not saving interested in full financing data in any models
        elif what_is_the_permission == "acquiring_limitedrights":
            run_permission_code = True
            # We are not saving interested in acquiring limited rights data in any models
        elif what_is_the_permission == "buying_all_rights":
            run_permission_code = True
            # We are not saving interested in buying all rights data in any models

        if run_permission_code:
            permission = blockpermission.objects.filter(
                related_showcase=show.showcase_id, user_id=request.user).exists()
            if not permission:
                permission = blockpermission()
                permission.user_id = request.user
                permission.related_showcase = show
                permission.save()
            permission = blockpermission.objects.get(
                related_showcase=show.showcase_id, user_id=request.user)
            if file == "sample_script":
                res = accept_reject(permission.sample_script,
                                    permission.sample_script_date, permission, file)
            if file == "story":
                res = accept_reject(
                    permission.story, permission.story_date, permission, file)

            if file == "full_script":
                res = accept_reject(permission.full_script,
                                    permission.full_script_date, permission, file)
            if file == "one_pager":
                res = accept_reject(permission.onepager,
                                    permission.onepager_date, permission, file)
            if file == "sample_footage":
                res = accept_reject(permission.sample_footage,
                                    permission.sample_footage_date, permission, file)
            if file == "sample_narration":
                res = accept_reject(permission.sample_narration,
                                    permission.sample_narration_date, permission, file)
            if file == "character_introduction":
                res = accept_reject(permission.character_introduction,
                                    permission.character_introduction_date, permission, file)
            if file == "script_analysis":
                res = accept_reject(permission.script_analysis,
                                    permission.script_analysis_date, permission, file)
            if file == "narrated_full_script":
                res = accept_reject(permission.narrated_full_script,
                                    permission.narrated_full_script_date, permission, file)
            if file == "pitchdeck":
                res = accept_reject(permission.pitchdeck,
                                    permission.pitchdeck_date, permission, file)
            if res[1] == 1:
                context = {"decrypted_url": res[0], "permission": "Allowed"}
            elif res[1] == 0:
                if file == "sample_script":
                    permission.sample_script = 0
                if file == "story":
                    permission.story = 0
                if file == "full_script":
                    permission.full_script = 0
                if file == "one_pager":
                    permission.onepager = 0
                if file == "sample_footage":
                    permission.sample_footage = 0
                if file == "sample_narration":
                    permission.sample_narration = 0
                if file == "character_introduction":
                    permission.character_introduction = 0
                if file == "script_analysis":
                    permission.script_analysis = 0
                if file == "narrated_full_script":
                    permission.narrated_full_script = 0
                if file == "pitchdeck":
                    permission.pitchdeck = 0
                permission.save()
                context = {"message": res[0], "permission": "Not Allowed"}
            elif res[1] == 2:
                context = {"message": res[0], "permission": "Not Allowed"}
            return JsonResponse(context)
        else:
            if file == "sample_script":
                samplescriptuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.samplescriptuploaded)
                # if res[1] == 1:
                #    return res[0]
                res = [samplescriptuploaded, 1]
            if file == "full_script":
                fullscriptuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.fullscriptuploaded)
                res = [fullscriptuploaded, 1]
            if file == "one_pager":
                onepageruploaded = ipfsUriDecrypt(
                    show.projecttitle, show.onepageruploaded)
                res = [onepageruploaded, 1]
            if file == "story":
                storyuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.storyuploaded)
                print(storyuploaded, "storyuploadeddecrypt")
                res = [storyuploaded, 1]
            if file == "sample_footage":
                samplefootageuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.samplefootageuploaded)
                res = [samplefootageuploaded, 1]
            if file == "sample_narration":
                samplenarrationuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.samplenarrationuploaded)
                res = [samplenarrationuploaded, 1]
            if file == "character_introduction":
                characterintrouploaded = ipfsUriDecrypt(
                    show.projecttitle, show.characterintrouploaded)
                res = [characterintrouploaded, 1]
            if file == "script_analysis":
                scriptanalysisuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.scriptanalysisuploaded)
                res = [scriptanalysisuploaded, 1]
            if file == "narrated_full_script":
                narratefulluploaded = ipfsUriDecrypt(
                    show.projecttitle, show.narratefulluploaded)
                res = [narratefulluploaded, 1]
            if file == "pitchdeck":
                pitchdeckuploaded = ipfsUriDecrypt(
                    show.projecttitle, show.pitchdeckuploaded)
                res = [pitchdeckuploaded, 1]

            context = {"decrypted_url": res[0], "permission": "Allowed"}
            return JsonResponse(context)
