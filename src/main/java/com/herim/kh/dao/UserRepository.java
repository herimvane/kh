package com.herim.kh.dao;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import com.herim.kh.domain.Position;
import com.herim.kh.domain.User;

public interface UserRepository extends JpaRepository<User, String> {

	User findByName(String name);
	List<User> findByPosition(Position position);
	
	@Query(value = "update user set status = ?1 where id= ?2 ", nativeQuery = true)  
	@Modifying  
	public void updateStatus(Integer status,String id);
	
	
	@Query(value = "update user set password = ?2 where id= ?1 ", nativeQuery = true)  
	@Modifying  
	public void updatePassword(String id,String password);
}
