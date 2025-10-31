# Guidelines for Mission Decomposition

Mission consists of one or multiple processes called **mission supportive processes**.
These processes are the key assets. Individual supportive processes can be mapped
to necessary **IT services** that can be consequently mapped to **supportive software components**
and their interactions.

Supportive processes should have their requirements on confidentiality, integrity,
and availability set. These requirements hold for the mission as a whole. However, they are
transitively mapped to cyber components during risk assessment.

We suppose that goals of enterprise missions (their functionality) can be achieved using
multiple alternative configurations of supportive processes, IT services, cyber components, and their interactions.
Allowable configurations of missions are defined using directed graph. Rules are expressed
using special AND / OR nodes and their edges in the graph.

Node AND requires presence of all referenced nodes in a configuration, e.g., IT services, cyber components.
OR nodes require presence of at least one out of referenced nodes representing supportive IT services 
and cyber components in a configuration.

## Example of Mission Decomposition
The process of defining mission decomposition can be explained on data from cyber defense exercise. Details about
the exercise are available in [Data in Brief](https://doi.org/10.1016/j.dib.2020.105784). There were six defensive 
(blue teams) that protected their identical networks. Figure 1 containing the network topology for team one 
is the most important for understanding this example. 

Figure 1 shows that the network is organized into four segments according to the role of hosts.
In this example, we can create a mission supportive process for each of these segments according to their roles.
The following [figure](mission_example.pdf) contains example decomposition of mission supportive processes
for DMZ and USR segments. The mission supportive processes are denoted by green colour, IT services by blue, and
supportive cyber components by red colour. Mission of **public-facing services** only requires functionality 
of its services. Therefore, its decomposition contains only AND nodes. Mission of **user services** 
requires functionality of its desktops. However, it is enough to have only one desktop of each type. 
Therefore, its decomposition contains OR nodes. The user services have four allowable configurations: 

<ul>
    <li>desktop1 and desktop3,</li>
    <li>desktop1 and desktop4,</li>
    <li>desktop2 and desktop3,</li>
    <li>desktop2 and desktop4.</li>
</ul>

It is possible to use combination of OR and AND nodes to express multiple combinations of IT services
that will provide functionality for a mission. Example can be found in 
[this paper](http://dx.doi.org/10.1145/3339252.3340522) in Figure 1. 
Mission supportive process of diagnostics uses one OR node that leads to two AND nodes
to express that diagnostics can be achieved using local or external cyber components.


## Mission Decomposition in JSON
When we had a complete mission decomposition expressed graphically, we created a JSON file that can be uploaded 
via REST API to database. The example for cyber defense exercise is available in 
[test data](../isim_rest/test/test_data/cyber_czech_mission_bt1.json).

The JSON file must contain two top-level keys - "nodes" and "relationships". 
The nodes should contain all nodes from [graphical representation of mission decomposition](mission_example.pdf): 

<ul>
    <li>mission supportive processes listed in part referenced by key "missions",</li>
    <li>IT services listed in part referenced by key "services",</li>
    <li>AND and OR nodes listed in "aggregations",</li>
    <li>supportive cyber components listed in "hosts".</li>
</ul>

First, it is necessary to assign IDs to each node. IDs do not have to follow any rules but should be unique.
We started to number IDs of missions, services, AND/OR nodes, and hosts from numbers that 
allow maintaining quick understanding of representation 
in [example JSON](../isim_rest/test/test_data/cyber_czech_mission_bt1.json). 

Properties of nodes are self-explaining. Criticality of missions can be expressed using two options. 
It is possible to use an overall criticality of a mission or separate confidentiality, integrity, 
and availability requirements but not both of these options simultaneously. 
The criticality should have value from 1 to 10.
Number 10 means the most critical mission which would cause a catastrophical impact to organization 
when not working properly. On the contrary, number 1 expresses a limited adverse impact to the organization. 
Numbers in the middle of the range indicate a serious adverse impact.
Confidentiality, integrity, and availability requirements are denoted instead 
of criticality using keys "confidentiality_requirement", "integrity_requirement", and "availability_requirement".
Individual requirements have values from 1 to 10. Number 10 means the most critical requirement. 
The organization would encounter catastrophic impact when the requirement is violated.  

Relationships have five subkeys:

<ul>
    <li>"one_way" that expresses directed edges from graphical representation of a mission,</li>
    <li>"two_way" that expresses allowed communication between two cyber components,</li>
    <li>"dependencies" that express dependency of one component on another cyber component,</li>
    <li>"supports" that express connections of missions to IT services even though there can be some AND/OR nodes 
between them,</li>
    <li>"has_identity" that expresses connections of IT services to cyber components even though 
there can be some AND/OR nodes between them.</li>
</ul>

Values used in relationships are names (in "supports", and "has_identity") 
or IDs (in "dependencies", "one_way", and "two_way"). "Two_way" relationships use keys "from" and "to" as "one_way" relationships.

# Identification of Entities

In order to create own decomposition of mission, it is necessary to identify what are 
mission supportive processes first. Mission supportive processes can have various names according
to goals of different organizations. However, when focusing on cybersecurity, we can focus
on network design. According to best practices, networks should be organized into segments. 
This organization into segments reveals what hosts and 
network services should be protected by hiding them from the Internet. Devices in one segment
can freely communicate with each other, hence the segments may indicate what are mission supportive processes.
For example, server segment usually contains important servers. We can identify which of them are important 
and should become cyber components. IT services will directly correspond to cyber components or will aggregate 
multiple components that serve as replicas. For example, in case of providing files (IT service) we could have 
primary file server (cyber component) and its backup servers (cyber components).
Finally, it is necessary to give a name to mission supportive process that aggregates all IT services, 
e.g., "critical servers".

Another approach for mission decomposition works in the opposite way.
We need to consider what cyber attacks would impact our organization.
Do we need to protect availability of services? Which services? Do we store sensitive data that should not be read or 
modified? In other words, it is necessary to identify cyber components that should have confidentiality, integrity, 
and availability requirements. Consequently, we can aggregate cyber components into IT services, 
and mission supportive processes, if any of components are related to each other.
