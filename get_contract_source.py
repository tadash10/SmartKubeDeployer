import argparse
import sys
from web3 import Web3, HTTPProvider
from solcx import compile_source
from kubernetes import client, config


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


def create_service_and_deployment(args):
    # Load Kubernetes configuration
    config.load_kube_config(args.kube_config)
    k8s_core_v1 = client.CoreV1Api()

    # Get contract source code
    if args.contract_file:
        with open(args.contract_file, "r") as f:
            contract_source = f.read()
    else:
        contract_source = args.contract_source

    # Deploy contract
    contract_address = deploy_contract(contract_source, args.contract_name, args.web3_provider)

    # Create Kubernetes service
    service_manifest = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": args.contract_name,
        },
        "spec": {
            "selector": {
                "app": args.contract_name
            },
            "ports": [{
                "protocol": "TCP",
                "port": 80,
                "targetPort": 8545
            }]
        }
    }

    k8s_core_v1.create_namespaced_service(namespace="default", body=service_manifest)

    # Create Kubernetes deployment
    deployment_manifest = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": args.contract_name,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app": args.contract_name
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": args.contract_name
                    }
                },
                "spec": {
                    "containers": [{
                        "name": args.contract_name,
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
                                        "name": args.secret_name,
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

    k8s_apps_v
