import argparse
import sys
import os
from web3 import Web3, HTTPProvider
from solcx import compile_source
from kubernetes import client, config


def get_contract_source(contract_file):
    with open(contract_file, "r") as f:
        contract_source = f.read()
    return contract_source


def get_web3_provider():
    default_provider = "http://localhost:8545"
    provider = input(f"Enter web3 provider URL (default: {default_provider}): ")
    if not provider:
        return default_provider
    return provider


def deploy_contract(contract_source, contract_name, web3_provider):
    compiled_sol = compile_source(contract_source)
    contract_interface = compiled_sol[f"<stdin>:{contract_name}"]
    bytecode = contract_interface["bin"]
    abi = contract_interface["abi"]
    web3 = Web3(HTTPProvider(web3_provider))

    # Unlock account if necessary
    if web3.eth.accounts[0] not in web3.eth.accounts:
        web3.personal.unlockAccount(web3.eth.accounts[0], "password")

    # Deploy contract
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = contract.constructor().transact({'from': web3.eth.accounts[0]})
    tx_receipt = web3.eth.waitForTransactionReceipt(tx_hash)
    contract_address = tx_receipt.contractAddress

    return contract_address


def deploy_deployment(k8s_apps_v1, name):
    deployment_manifest = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app": name
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": name
                    }
                },
                "spec": {
                    "containers": [{
                        "name": name,
                        "image": "ethereum/client-go:v1.9.3",
                        "args": [
                            "--rpc",
                            "--rpcaddr",
                            "0.0.0.0",
                            "--rpccorsdomain",
                            "*",
                            "--rpcapi",
                            "eth,net,web3,personal"
                        ],
                        "env": [
                            {
                                "name": "ETH_NETWORK_ID",
                                "value": "1"
                            },
                            {
                                "name": "ETH_KEYSTORE_PASSWORD",
                                "valueFrom": {
                                    "secretKeyRef": {
                                        "name": "geth-secret",
                                        "key": "password"
                                    }
                                }
                            }
                        ],
                        "ports": [{
                            "name": "rpc",
                            "containerPort": 8545,
                            "protocol": "TCP"
                        }]
                    }]
                }
            }
        }
    }
    k8s_apps_v1.create_namespaced_deployment(namespace="default", body=deployment_manifest)


def create_service_and_deployment(args):
    # Load Kubernetes configuration
    config.load_kube_config(args.kube_config)
    k8s_core_v1 = client.CoreV1Api()
    k8s_apps_v1 = client.AppsV1Api()

    # Deploy contract
    contract_source = get_contract_source(args.contract_file)
    contract_address = deploy_contract(contract_source, args.contract_name, args.web3_provider)

    # Create Kubernetes service
    service_manifest = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata":
