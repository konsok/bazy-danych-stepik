from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
load_dotenv()
app = Flask(__name__)
uri = os.getenv('URI')
user = os.getenv("USERNAME")
password = os.getenv("PASSWORD")
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "test1234"), database="neo4j")

@app.route('/')
def initial():
    return 'Neo4j Flask API, by Konrad Sokolowski. You can visit /employees to see all employees and /departments to see all departments.'

def get_employees(tx, name=None, role=None, department=None, sort=None):
    query = "MATCH (e: Employee)"
    conditions = []
    if name is not None:
        conditions.append("toLower(e.name) CONTAINS toLower($name)")
    if role is not None:
        conditions.append("toLower(e.role) CONTAINS toLower($role)")
    if department is not None:
        conditions.append("toLower(d.department) CONTAINS toLower($department)")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " RETURN e, ID(e) as id"
    if sort == "name_asc":
        query += " ORDER BY e.name"
    elif sort == "name_desc":
        query += " ORDER BY e.name DESC"
    results = tx.run(query, name=name, role=role, department=department).data()
    employees = [{"name": result['e']['name'],
                  "role": result['e']['role'],
                  "department": result['e']['department'],
                  "id": result['id']} for result in results]
    return employees


@app.route('/employees', methods=['GET'])
def get_employees_route():
    name = request.args.get('name')
    role = request.args.get('role')
    department = request.args.get('department')
    sort = request.args.get('sort')
    with driver.session() as session:
        employees = session.read_transaction(get_employees, name, role, department, sort)
    response = {'employees': employees}
    return jsonify(response)


def add_employee(tx, name, role, department):
    query = "MERGE (e:Employee {name:$name, role:$role, department:$department})" \
            "MERGE (d:Department {name:$department}) " \
            "MERGE (e)-[:WORKS_IN]->(d)"
    tx.run(query, name=name, role=role, department=department)


@app.route('/employees', methods=['POST'])
def add_employee_route():
    if request.json is None:
        return jsonify({"error": "Request body is empty"}), 400
    name = request.json.get("name")
    role = request.json.get("role")
    department = request.json.get("department")
    if name is None or role is None or department is None:
        return jsonify({"error": "Not all required fields have been provided"}), 400
    with driver.session() as session:
        result = session.run("MATCH (e:Employee) WHERE e.name = $name RETURN COUNT(e) as count", name=name).single()
        if result['count'] > 0:
            return jsonify({"error": "Employee already exists."}), 400
        session.write_transaction(add_employee, name, role, department)
        return jsonify({"message": "Employee added successfully."}), 201


def update_employee(tx, employee_id, name=None, role=None, department=None):
    query = "MATCH (e: Employee) WHERE ID(e) = $employee_id"
    if name is not None or role is not None or department is not None:
        query += " SET "
        updates = []
        if name is not None:
            updates.append("e.name = $name")
        if role is not None:
            updates.append("e.role = $role")
        if department is not None:
            updates.append("e.department = $department")
        query += ", ".join(updates)
    result = tx.run(query, employee_id=employee_id, name=name, role=role, department=department)
    if result.consume().counters.nodes_created > 0:
        return {"error": "Employee not found"}
    return {"message": "Employee updated successfully"}


@app.route('/employees/<int:id>', methods=['PUT'])
def update_employee_route(id):
    name = request.json.get('name')
    role = request.json.get('role')
    department = request.json.get('department')
    with driver.session() as session:
        res = session.run("MATCH (e:Employee) MATCH (e) WHERE ID(e) = $id RETURN e",
                          id=id).single()
        if res is None:
            return jsonify({"error": "Employee not found."}), 400
        result = session.write_transaction(update_employee, id, name, role, department)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result), 200


def delete_employee(tx, id, department_name=None):
    if department_name is not None:
        query = "MATCH (e: Employee)-[r:MANAGES]->(d:Department)" \
                "WHERE ID(e) = $id " \
                "DETACH DELETE e, d"
    else:
        query = "MATCH (e: Employee) WHERE ID(e) = $id DETACH DELETE e"
    tx.run(query, id=id, department_name=department_name)


@app.route('/employees/<int:id>', methods=['DELETE'])
def delete_employee_route(id):
    with driver.session() as session:
        result = session.run("MATCH (e:Employee) WHERE ID(e) = $id RETURN COUNT(e) as count", id=id).single()
        if result["count"] == 0:
            return jsonify({"error": "Employee not found."}), 404
        result = session.run("MATCH (e:Employee)-[r:MANAGES]->(d:Department)"
                             " WHERE ID(e) = $id RETURN d.name", id=id).single()
        if result is None:
            session.write_transaction(delete_employee, id)
            return jsonify({"message": "Employee deleted successfully"}), 200
        else:
            department_name = result["d.name"]
            print(department_name)
            session.write_transaction(delete_employee, id, department_name)
            return jsonify({"message": f"Employee and its department {department_name} deleted successfully."}), 200


@app.route('/employees/<int:id>/subordinates', methods=['GET'])
def get_subordinates(id):
    with driver.session() as session:
        result = session.run("MATCH (m:Employee)-[r:MANAGES]->(d:Department) WHERE ID(m) = $id "
                             "RETURN d.name as department_name", id=id).single()
        if not result:
            return jsonify({"error": "Employee not found or has no department to manage"}), 404
        department_name = result["department_name"]
        query = "MATCH (e:Employee)-[r:WORKS_IN]->(d:Department) " \
                "WHERE d.name = $department_name RETURN e.name as name"
        results = session.run(query, department_name=department_name).data()
        subordinates = [{"name": result["name"]} for result in results]
        return jsonify(subordinates), 200


@app.route('/employees/<int:id>', methods=['GET'])
def get_employee_info(id):
    with driver.session() as session:
        query = "MATCH (e:Employee)-[r:WORKS_IN]->(d:Department)<-[:MANAGES]-(m:Employee)," \
                "(em:Employee)-[rel:WORKS_IN]->(d)" \
                "WHERE ID(e) = $id " \
                "RETURN d.name as department_name, m.name as manager," \
                " count(rel) as number_of_employees"
        result = session.run(query, id=id).single()
        if not result:
            return jsonify({"error": "Employee not found or has no department"}), 404
        department_name = result["department_name"]
        manager = result["manager"]
        number_of_employees = result["number_of_employees"]
        return jsonify({"department_name": department_name, "manager": manager,
                        "number_of_employees": number_of_employees}), 200


def get_departments(tx, name=None, sort=None):
    query = "MATCH (e:Employee)-[r]->(d:Department)"
    conditions = []
    if name is not None:
        conditions.append("toLower(d.name) CONTAINS toLower($name)")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " RETURN d.name as name, count(r) as number_of_employees,  ID(d) as id"
    if sort == "name_asc":
        query += " ORDER BY d.name"
    elif sort == "name_desc":
        query += " ORDER BY d.name DESC"
    elif sort == "e_asc":
        query += " ORDER BY number_of_employees"
    elif sort == "e_desc":
        query += " ORDER BY number_of_employees DESC"
    results = tx.run(query, name=name).data()
    departments = [{"name": result['name'], "number_of_employees": result['number_of_employees'], "id": result['id']} for result in results]
    return departments


@app.route('/departments', methods=['GET'])
def get_departments_route():
    name = request.args.get('name')
    sort = request.args.get('sort')

    with driver.session() as session:
        departments = session.read_transaction(get_departments, name, sort)
        return jsonify(departments), 200


def get_employees_by_department(tx, id):
    query = "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) WHERE ID(d) = $id RETURN e"
    results = tx.run(query, id=id).data()
    employees = [{"name": result['e']['name'], "role": result['e']['role']} for result in results]
    return employees


@app.route('/departments/<int:id>/employees', methods=['GET'])
def get_department_employees(id):
    with driver.session() as session:
        employees = session.read_transaction(get_employees_by_department, id)
        return jsonify(employees), 200


if __name__ == '__main__':
    app.run()
