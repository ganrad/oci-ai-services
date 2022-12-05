# Detect Anomalies using Async Inference Feature

This tutorial details the steps for detecting anomalies in inference data sets using OCI Anomaly Detection Service **Asynchronous Inference** feature.

The terms **Detecting Anomalies** and **Inferencing** are used interchangably in the remainder of this tutorial to mean one and the same thing - Detecting anomalies in time series data.

Asynchronous Inference feature can be used with both Univariate and Multivariate inference data sets.

Typical use cases or scenarios where users can benefit from using Asynchronous Inference are listed below.
- Large inference data sets
  The maximum number of data points supported by the *detectAnomalies* synchronous API is 30K.  This may impose restrictions in anomaly detection scenarios where a large number of data points typically in the millions need to be inferenced.
- 

At a high level, the process for detecting anomalies using Asynchronous inferencing involves the steps outlined below.
- Training a model with a **Training** data set.
  Refer to the other tutorials for training an anomaly detection model.
- Detect anomalies with an **Inference** data set.
  Use the Asynchronous Inference API (AD Service SDK) or OCI Console to create an Asynchronous Job.

In this tutorial, we will use the OCI Console for creating an Asynchronous Inference Job. The high level steps are as follows.

1. Upload an inference data set to an OCI Object Store Bucket
2. Create an Asynchronous Job
3. Confirm Anomaly Detection results

## Before You Begin
To work on this tutorial, you must have the following
- A paid Oracle Cloud Infrastructure (OCI) account, or a new accont with Oracle Cloud Promotions.  See [Request and Manage Free Oracle Cloud Promotions](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup.htm).
- Administrator privilege for the OCI account
- At least one user in your tenancy who wants to access Anomaly Detection Service. This user must be created in [IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingusers.htm)

## Pre-requisites
- By default, only users in the **Administrators** group have access to all Anomaly Detection resources. If you are not an admin user, you will need to request your administrator to create OCI policies and assign them to your group.  Please refer to the instructions in the [About Anomaly Detection Policies](https://docs.oracle.com/en-us/iaas/Content/anomaly/using/policies.htm) page.
- You must have a compartment which you will be using to provision required resources while going through the labs in this tutorial. Refer to OCI documentation to learn about [Managing Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm).

**IMPORTANT**: Before proceeding, make sure you have trained an Anomaly Detection Model by following the steps in the Univariate Anomaly Detection tutorial.

## 1. Upload Inference Data Set to an OCI Object Store Bucket

   1. Login to [OCI Console](https://cloud.oracle.com) using your credentials
         
      After logging into OCI, you should see the home web page as shown in the screenshot below.
         
      ![alt tag](./images/section-1-1.png)

   2. Store the inference data set in OCI Object Store Bucket

      Download one of the sample inference data sets from the Univariate tutorial and save it locally on your workstation. For the purposes of this tutorial, we will be using the inference data set for use case no. 4 (Monitor Blood Glucose Levels).  This use case pertains to detecting abnormal blood glucose levels (anomalies) in a patient's blood data. In case you trained the anomaly detection model with a different data set, check to make sure you are using the corresponding inference data set.

      Click on the hamburger icon on the top left and then click on **Storage** in the display menu.  See screenshot below.

      ![alt tag](./images/section-1-2-1.png)

      Then click on **Buckets** under **Object Storage & Archive Storage**.  This will take you to the **Buckets** page as shown in the screenshot below.

      ![alt tag](./images/section-1-2-2.png)

      Click on **Create Bucket** button to create a new Bucket for storing training data files. You can either use the default name or specify a name for the bucket.  Leave the other fields as is and then click on **Create**.  The new bucket should get created and be listed in the *Buckets* page as shown in the screenshot below.

      ![alt tag](./images/section-1-2-3.png)

      In the **Buckets** page, click on the bucket (link) which you created in the previous step. Under Objects, click on the **Upload** button. In the *Upload* Objects panel, specify a name for the file (optional) you want to upload to OCI Object Storage. Then select the inference file from your local directory and click **Upload**. Once the file gets uploaded, click on the **Close** button to close the file upload panel. The uploaded file should be listed in the *Objects* page as shown in the screenshot below.
       
      ![alt tag](./images/section-1-2-4.png)

## 2. Create an Asynchronous Job


## 3. Confirm Anomaly Detection Results
   

      Next, use your own time-series inference data sets to create Asynchronous Jobs and perform inference.
