# """
# Discharge orders data and related functionality for the PostOp AI system
# """
# from dataclasses import dataclass, field
# from typing import List, Optional, Dict, Any

# @dataclass
# class DischargeOrder:
#     id: str
#     label: str
#     discharge_order: str
    
#     # New call scheduling fields
#     generates_calls: bool = False
#     call_template: Optional[Dict[str, Any]] = None
    
#     # Backward compatibility - keep existing fields
#     day_offset: int = 0
#     send_at_hour: int = 9

# # Real discharge orders from venous malformation case
# DISCHARGE_ORDERS = [
#     DischargeOrder(
#         id="vm_discharge", 
#         label="Venous Malformation Discharge Order", 
#         discharge_order="May discharge patient home under the care of a responsible parent/legal guardian after 1.5 hours if patient meets discharge criteria: Stable vital signs, Ambulatory or at pre-procedure status, Tolerating oral intake, Patient has voided at least once, Puncture site stable without bleeding.",
#         day_offset=0, 
#         send_at_hour=18
#     ),
#     DischargeOrder(
#         id="vm_symptoms", 
#         label="Symptoms to Report", 
#         discharge_order="Contact Primary Care or Specialty Care Doctor for: Temperature over 100.5, Pain not relieved by medication, Difficulty breathing, Nausea/Vomiting, Drainage or foul odor from dressing/incision, painful swelling at the incision site, excessive discoloration of the skin. In Case of an urgent concern or emergency, call 911 or come to the Egleston Emergency Room.",
#         day_offset=0, 
#         send_at_hour=20
#     ),
#     DischargeOrder(
#         id="vm_compression", 
#         label="Compression Bandage Instructions", 
#         discharge_order="Leave the compression bandage on for 24 hours and then wear as much as can be tolerated for 7 days.",
#         generates_calls=True,
#         call_template={
#             "timing": "24_hours_after_discharge",
#             "call_type": "discharge_reminder",
#             "priority": 2,
#             "prompt_template": "You are calling {patient_name} to remind them about their compression bandage. They were instructed: '{discharge_order}'. It's been about 24 hours since their procedure. Ask if they've removed the compression bandage as instructed and if they have any questions about the next steps."
#         },
#         day_offset=1, 
#         send_at_hour=9
#     ),
#     DischargeOrder(
#         id="vm_shower", 
#         label="Bathing Instructions", 
#         discharge_order="May shower tomorrow, no bathing or swimming for 5 days.",
#         day_offset=1, 
#         send_at_hour=10
#     ),
#     DischargeOrder(
#         id="vm_activity", 
#         label="Activity Restrictions", 
#         discharge_order="Routine, Normal, Elevate the extremity whenever possible. Minimal weight-bearing for 48 hours. Walking only for 7 days. May resume normal activities after 7 days.",
#         generates_calls=True,
#         call_template={
#             "timing": "48_hours_after_discharge",
#             "call_type": "discharge_reminder", 
#             "priority": 2,
#             "prompt_template": "You are calling {patient_name} about their activity restrictions. You want to remind them: '{discharge_order}'. It's been 48 hours since their procedure. Ask how they're managing the minimal weight-bearing restriction and if they have any questions about resuming normal activities."
#         },
#         day_offset=1, 
#         send_at_hour=11
#     ),
#     DischargeOrder(
#         id="vm_school", 
#         label="Return to School/Daycare", 
#         discharge_order="May Return to School/Daycare: 6/23/2025",
#         generates_calls=True,
#         call_template={
#             "timing": "day_before_date:2025-06-23",
#             "call_type": "discharge_reminder",
#             "priority": 2, 
#             "prompt_template": "You are calling {patient_name} to remind them about returning to school/daycare. They were told: '{discharge_order}'. Tomorrow is the day they may return to school or daycare. Ask if they're feeling ready and if they have any concerns about returning."
#         },
#         day_offset=7, 
#         send_at_hour=14
#     ),
#     DischargeOrder(
#         id="vm_medication", 
#         label="Medication Instructions", 
#         discharge_order="Starting 8 hours from last Toradol dose (unless on anticoagulation therapy), take ibuprofen per the instructions on the medication bottle for 7 days, regardless of whether or not your child is having pain. Pain is usually more severe 5-15 days after the procedure. In approximately 14 days, you are likely to feel firm nodules in the area of the venous malformation. These represent scar tissue.",
#         generates_calls=True,
#         call_template={
#             "timing": "daily_for_3_days_starting_8_hours_after_discharge",
#             "call_type": "medication_reminder",
#             "priority": 2,
#             "prompt_template": "You are calling {patient_name} about their medication schedule. They were instructed: '{discharge_order}'. This is a reminder to take their ibuprofen as prescribed. Ask if they've been taking it regularly and if they have any questions about the medication or pain management."
#         },
#         day_offset=0, 
#         send_at_hour=21
#     ),
#     DischargeOrder(
#         id="vm_bleomycin", 
#         label="Bleomycin Precautions", 
#         discharge_order="Please do not remove EKG leads and any other adhesive for 48 hours. Also, bleomycin can cause a transient rash. If your child develops a rash/skin discoloration, please notify the Vascular Anomalies Clinic (404 785-8926). The rash/skin discoloration can take weeks to months to resolve.",
#         generates_calls=True,
#         call_template={
#             "timing": "daily_for_2_days_starting_12_hours_after_discharge",
#             "call_type": "discharge_reminder",
#             "priority": 2,
#             "prompt_template": "You are calling {patient_name} about their EKG leads and bleomycin precautions. They were instructed: '{discharge_order}'. This is a daily reminder to keep the EKG leads on for the full 48 hours. Ask if they've kept the leads on and if they've noticed any skin changes or rash."
#         },
#         day_offset=0, 
#         send_at_hour=22
#     ),
# ]

# # Doctor-selected orders for this specific patient (based on checked items in discharge orders)
# SELECTED_DISCHARGE_ORDERS = [
#     # "vm_discharge",      # ✓ Venous Malformation (lower extremity) Discharge Order
#     "vm_symptoms",       # ✓ Discharge Instruction (symptoms to report)
#     "vm_compression",    # ✓ Discharge Instruction (compression bandage)
#     "vm_shower",         # ✓ May Shower
#     "vm_activity",       # ✓ Discharge Activity Instructions
#     "vm_school",         # ✓ Discharge - Return To School Or Daycare
#     "vm_medication",     # ✓ Discharge Instruction (medication)
#     "vm_bleomycin",      # ✓ Discharge Instruction (bleomycin precautions)
# ]

# def get_order_by_id(order_id: str) -> DischargeOrder:
#     """Get a discharge order by its ID"""
#     for order in DISCHARGE_ORDERS:
#         if order.id == order_id:
#             return order
#     raise ValueError(f"Discharge order with ID '{order_id}' not found")

# def get_selected_orders() -> List[DischargeOrder]:
#     """Get all doctor-selected discharge orders"""
#     return [get_order_by_id(order_id) for order_id in SELECTED_DISCHARGE_ORDERS]