# Detect Anomalies in Univariate time series data (signals)

This tutorial details the steps for detecting anomalies in **Univariate** signals using *OCI Anomaly Detection Service*.

Univariate anomaly detection (UAD) refers to the problem of identifying anomalies in a single time series data.  A single time series data contains timestamped values for one signal (a.k.a metric or measure).

At a high level, the process of detecting anomalies in time series data using OCI Anomaly Detection Service involves two simple steps
- Training a model with a **Training** data set.
  The training data set should ideally not contain any anomalies. It should contain values that were collected when the monitoried system/asset was operating under normal conditions.  It's ok to include data values that represent normal seasonal trends & other values that represent normal conditions. 
- Using the trained model to detect anomalies with an **Inference** data set.
  The inference data set contains timestamped data values for a given signal typically collected by a sensor or software agent which is monitoring a target system/asset (Physical or Virtual) in real-time.

With OCI Anomaly Detection Service, users can
- Train univariate anomaly detection models using different types of univariate time series data (See Section 1 below)
- Detect different types of anomalies in time series data such as point, range and contextual anomalies
- Train models for up to 300 univariate signals using one data set stored in an OCI Object Store file or OCI Autonomous Database table
- Infer upon or detect anomalies in 300 individual time series data (~ signals) using a single **detect anomalies** api call

In this tutorial, we will go thru the following steps.
<!--ts-->
  * 1. Review univariate time series data patterns and anomaly types
  * 2. Review time series data sets
  * 3. Train an Anomaly Detection Model using OCI Console
  * 4. Run inference and detect anomalies using OCI Console
  * 5. Confirm OCI Anomaly Detection Service has correctly identified the anomalies in the inference data set
<!--te-->

## Before You Begin
To work on this tutorial, you must have the following
- A paid Oracle Cloud Infrastructure (OCI) account, or a new accont with Oracle Cloud Promotions.  See [Request and Manage Free Oracle Cloud Promotions](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup.htm).
- Administrator privilege for the OCI account
- At least one user in your tenancy who wants to access Anomaly Detection Service. This user must be created in [IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingusers.htm)

## Pre-requisites
- By default, only users in the **Administrators** group have access to all Anomaly Detection resources. If you are not an admin user, you will need to request your administrator to create OCI policies and assign them to your group.  Please refer to the instructions in the [About Anomaly Detection Policies](https://docs.oracle.com/en-us/iaas/Content/anomaly/using/policies.htm) page.

## 1. Review time series data patterns and anomaly types
   OCI Anomaly Detection Service can detect anomalies in different types/patterns of univariate time series data.  Furthermore, the service can identify different types of anomalies in the data with minimal false alarms.

   Refer to the table below for time series data patterns and anomaly types detected by OCI Anomaly Detection Service.

   - A data set containing seasonal patterns.
     OCI Anomaly Detection Service detects spikes and dips in time series data containing seasonal patterns. The univariate kernel does automatic window size detection and as a result anomalous spikes are detected as soon as they occur (no delay) with high precision as shown in the train and test graphs below.

     ![alt tag](./images/A-01.PNG)

     ![alt tag](./images/A-01.PNG)

   - A flat trend (or constant) data set.
     OCI Anomaly Detection Service detects anomalies in flat (or constant) trend data as shown in the train and test graphs below. 

   - A continuously increasing linear trend data set. No anomalies detected (No false alarms!)
     OCI Anomaly Detection Service detects increasing linear trends in data values and doesn't flag any anomalies. 

   - A linear trend data set. Detect anamalous spikes and dips.
     OCI Anomaly Detection Service detects anomalous values (spikes and dips) in linear time series data.

## 2. Review time series data sets
   Here will review time series data patterns along with types of anomalies which can be detected by OCI Anomaly Detection Service.

   Use Case | Description | Data Pattern | Anomaly Type | Data Sets
   -------- | ----------- | ------------ | ------------ | ---------
   Network Service Usage | Identify anomalies in network service metrics - Bytes received/transmitted | Seasonal trend | Spikes | ./data/network_svc_usage_train.csv ./data/network_svc_usage_test.csv
   Compute Service Usage | Identify anomalies in compute metrics for database VM - Memory Consumption | Increasing Linear trend | ./data/database_vm_train.csv ./data/database_vm_test.csv

