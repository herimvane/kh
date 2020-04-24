package com.herim.kh.dao;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import com.herim.kh.domain.Operation;

public interface OperationRepository extends JpaRepository<Operation, String> {
	
	Operation findByNameAndStatus(String name,Integer status);
	
	@Query(value = "update operation set status = ?2 where name= ?1 ", nativeQuery = true)  
	@Modifying  
	public void updateStatus(String name,Integer status);
}
