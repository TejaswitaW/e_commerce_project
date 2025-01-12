import json

from account.models import Address
from basket.basket import Basket
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from orders.models import Order, OrderItem

from .models import DeliveryOptions


@login_required
def deliverychoices(request):
    deliveryoptions = DeliveryOptions.objects.filter(is_active=True)
    return render(request, "checkout/delivery_choices.html", {"deliveryoptions": deliveryoptions})


@login_required
def basket_update_delivery(request):
    # Getting the information from the Basket class
    basket = Basket(request)
    # Checking the ajax request
    if request.POST.get("action") == "post":
        # Extracting data from Ajax request
        # Setting up new variable delivery option
        delivery_option = int(request.POST.get("deliveryoption"))
        delivery_type = DeliveryOptions.objects.get(id=delivery_option)
        # New function in Basket class basket_update_delivery, returns total price after update
        updated_total_price = basket.basket_update_delivery(delivery_type.delivery_price)

        # Getting the session information from django
        session = request.session
        # Adding new data purchase, if purchase option is not in the session
        if "purchase" not in request.session:
            session["purchase"] = {
                "delivery_id": delivery_type.id,
            }
        else:
            # If purchase already exist we just want to update it.
            session["purchase"]["delivery_id"] = delivery_type.id
            # Tell django we have modified the session
            session.modified = True

        # Sent data to template
        response = JsonResponse({"total": updated_total_price, "delivery_price": delivery_type.delivery_price})
        return response


@login_required
def delivery_address(request):

    session = request.session
    # Allow to select address if user has selected delivery option, if not, user is redirected to previous page
    if "purchase" not in request.session:
        messages.success(request, "Please select delivery option")
        return HttpResponseRedirect(request.META["HTTP_REFERER"])

    addresses = Address.objects.filter(customer=request.user).order_by("-default")

    # If address is not in the session then add that into session.
    if "address" not in request.session:
        # Default address is selecting as an address
        session["address"] = {"address_id": str(addresses[0].id)}
    else:
        # If already exist , we are just updating the address id(as selected address goes at the top)
        session["address"]["address_id"] = str(addresses[0].id)
        session.modified = True

    return render(request, "checkout/delivery_address.html", {"addresses": addresses})


@login_required
def payment_selection(request):

    session = request.session
    # If address is not in session then we are going to send user back again.
    if "address" not in request.session:
        messages.success(request, "Please select address option")
        return HttpResponseRedirect(request.META["HTTP_REFERER"])

    return render(request, "checkout/payment_selection.html", {})


####
# PayPay
####
from paypalcheckoutsdk.orders import OrdersGetRequest

from .paypal import PayPalClient


@login_required
def payment_complete(request):
    PPClient = PayPalClient()

    body = json.loads(request.body)
    # We got orderID from ajax request body.
    data = body["orderID"]
    user_id = request.user.id

    # OrdersGetRequest this is paypal function.
    # Gives data about that particular payment.
    requestorder = OrdersGetRequest(data)
    # Response from paypal, we have all the data about that transaction.
    response = PPClient.client.execute(requestorder)

    # We can grab information from that.
    total_paid = response.result.purchase_units[0].amount.value

    basket = Basket(request)
    # Saving information into our database.
    order = Order.objects.create(
        user_id=user_id,
        full_name=response.result.purchase_units[0].shipping.name.full_name,
        email=response.result.payer.email_address,
        address1=response.result.purchase_units[0].shipping.address.address_line_1,
        address2=response.result.purchase_units[0].shipping.address.admin_area_2,
        postal_code=response.result.purchase_units[0].shipping.address.postal_code,
        country_code=response.result.purchase_units[0].shipping.address.country_code,
        total_paid=response.result.purchase_units[0].amount.value,
        order_key=response.result.id,
        payment_option="paypal",
        billing_status=True,
    )
    order_id = order.pk

    # Now we are going to take all the products from the basket, and store in the joining table to the order
    # The order and all the items in the order.
    for item in basket:
        OrderItem.objects.create(order_id=order_id, product=item["product"], price=item["price"], quantity=item["qty"])

    return JsonResponse("Payment completed!", safe=False)


@login_required
def payment_successful(request):
    basket = Basket(request)
    # Payment has been done for items , so remove them session data
    basket.clear()
    return render(request, "checkout/payment_successful.html", {})
