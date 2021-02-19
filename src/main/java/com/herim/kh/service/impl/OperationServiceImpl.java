package com.herim.kh.service.impl;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.herim.kh.dao.OperationRepository;
import com.herim.kh.domain.Operation;
import com.herim.kh.service.OperationService;

@Service
public class OperationServiceImpl implements OperationService {
	
	@Autowired
	private OperationRepository operationRepository;

	@Override
	public Boolean haveOperation(String name, Integer status) {
		return operationRepository.findByNameAndStatus(name,status) == null ? false : true;
	}
	
	@Override
	public Operation getByName(String name) {
		return operationRepository.findByName(name);
	}
	
	@Transactional
	@Override
	public void update(String name, Integer status) {
		operationRepository.updateStatus(name, status);
	}
	
	@Override
	public void save(Operation operation) {
		operationRepository.save(operation);
	}

}
