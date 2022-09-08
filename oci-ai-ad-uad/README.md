# Detect anomalies in Univariate time series data (signals)

This tutorial details the steps for detecting anomalies in **Univariate** signals using *OCI Anomaly Detection Service*.

Univariate anomaly detection (UAD) refers to the problem of identifying anomalies in a single time series data.  A single time series data contains timestamped values for one signal (a.k.a metric or measure).

At a high level, the process of detecting anomalies in time series data involves
- Training a model with a **training** data set.
  The training data set should ideally not contain any anomalies. It should contain values that were collected when the monitoried system/asset was operating under normal conditions.  It's ok to include data values that represent normal seasonal trends & other values that represent conditions considered normal. 
- Using the trained model to detect anomalies with an **inference** data set.
  The inference data set contains timestamped data values for a given signal typically collected by a sensor or software agent which is monitoring a target system/asset in real-time.

With OCI Anomaly Detection Service, users can
- Train univariate anomaly detection models using different types of univariate time series data (See Section 1 below)
- Detect different types of anomalies in time series data
- Train models for up to 300 univariate signals using one data set
- Infer upon or detect anomalies in 300 individual time series data (~ signals) using a single **detect anomalies** api call

In this tutorial, we will go thru the following steps.
1. Review time series data patterns and anomaly types
2. Train an Anomaly Detection Model
3. Run inference and detect anomalies
4. Confirm detected anomalies are actual anomalies in the OCI Console


## 1. Review time series data patterns and anomaly types
   OCI Anomaly Detection Service can detect anomalies in different types of time series data.  Furthermore, the service can identify different types of anomalies in the data with minimal false alarms.

   Refer to the table below for time series data patterns and anomaly types detected by OCI Anomaly Detection Service.

   - A data set containing seasonal patterns.  Detect anomalous spikes in the seasonal pattern.
     OCI Anomaly Detection Service detects spikes and dips in time series data containing seasonal patterns. The univariate kernel does automatic window size detection and as a result anomalous spikes are detected as soon as they occur (no delay) with high precision as shown in the train and test graphs below.

     ![alt tag](./images/A-01.PNG)

     ![alt tag](./images/A-01.PNG)

   - A flat trend data set. Detect continuous anomalies.
     OCI Anomaly Detection Service detects anomalies in flat (or constant) trend data as shown in the train and test graphs below. 

   - A continuously increasing linear trend data set. No anomalies detected (No false alarms!)
     OCI Anomaly Detection Service detects 

   - A linear trend data set. Detect anamalous spikes and dips.
